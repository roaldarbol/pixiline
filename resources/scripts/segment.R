#!/usr/bin/env Rscript
# Step 5 - segment + classify each processed recording, writing the final CSVs.
#
#   pixi run segment                 # scans data/output
#   pixi run segment <output-base>   # scans a custom output base
#   pixi run segment --overwrite     # rewrite outputs that already exist
#
# For every recording under <base>/<stem>/tracking/processed/<stem>.parquet this:
#   1. cleans the tracks and calculates features          (R/features.R)
#   2. segments sleep vs wake, unsupervised               (changepoints + 2-means)
#   3. detects active bouts within the main sleep period  (find_bouts, canonical)
#   4. classifies each bout Awake / REM / uncertain       (models/awake_classifier.rds)
# and writes, into <base>/<stem>/segments/:
#   <stem>_sleepwake.csv  - the sleep/wake anievent (one row per Sleep/Awake segment)
#   <stem>_bouts.csv      - THE FINAL ANIEVENT: one row per active bout, with its
#                           classified state and all per-bout features
#
# This is the apply-only path extracted from segmentation.qmd. It does NOT train
# anything and needs no annotations - it loads the already-trained classifier.

suppressPackageStartupMessages({
  library(animovement)
  library(tidyverse)
  library(tidychangepoint)
  library(tidyclust)
  library(tidymodels)
})

script_dir   <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1]))
project_root <- normalizePath(file.path(script_dir, "..", ".."))   # resources/scripts -> root

# Apply-path helpers only (no training / evaluation / plotting code).
source(file.path(script_dir, "R", "features.R"))         # clean_tracks, calculate_features
source(file.path(script_dir, "R", "changepoints.R"))     # detect_changepoints
source(file.path(script_dir, "R", "segment-features.R")) # cluster_segments, label_segments, compact_bout_features
source(file.path(script_dir, "R", "classification.R"))   # classify_states

cfg <- yaml::read_yaml(file.path(project_root, "config.yaml"))$segment

args       <- commandArgs(trailingOnly = TRUE)
overwrite  <- "--overwrite" %in% args
# Optional --stem <name>: restrict processing to a single recording's folder
# instead of every recording under <base>. The GUI passes this so each video is
# an independent job; on the command line it is simply omitted to scan them all.
stem_idx    <- match("--stem", args)
stem_filter <- if (!is.na(stem_idx) && stem_idx < length(args)) args[stem_idx + 1] else NA_character_
drop_idx    <- if (!is.na(stem_idx)) c(stem_idx, stem_idx + 1) else integer(0)
positional  <- args[setdiff(seq_along(args), drop_idx)]
positional  <- positional[!startsWith(positional, "--")]
base_dir   <- if (length(positional) >= 1) positional[[1]] else file.path(project_root, "output")

classifier <- readRDS(file.path(project_root, cfg$classifier))
thr_cut    <- cfg$awake_threshold
reject     <- cfg$reject_band

# Effective sampling rate (Hz), derived per recording from the `time` column.
# The median frame interval is robust to the frames the tracker drops, so this
# recovers the true rate whether `time` came from real timestamps or the FPS
# probe in preprocess.R.
derive_sampling_rate <- function(time) {
  step <- stats::median(diff(sort(unique(time))), na.rm = TRUE)
  if (!is.finite(step) || step <= 0) cli::cli_abort("Could not derive a sampling rate from `time`.")
  1 / step
}

stems <- basename(list.dirs(base_dir, recursive = FALSE))
if (!is.na(stem_filter)) stems <- stems[stems == stem_filter]

for (stem in stems) {
  parquet <- file.path(base_dir, stem, "tracking", "processed", paste0(stem, ".parquet"))
  if (!file.exists(parquet)) {
    cli::cli_inform("Skipping {stem}: no processed parquet (run preprocess first).")
    next
  }
  out_dir   <- file.path(base_dir, stem, "segments")
  bouts_out <- file.path(out_dir, paste0(stem, "_bouts.csv"))
  sw_out    <- file.path(out_dir, paste0(stem, "_sleepwake.csv"))
  if (!overwrite && file.exists(bouts_out)) {
    cli::cli_inform("Skipping {stem}: already segmented (use --overwrite to rebuild).")
    next
  }

  cli::cli_h1("Segmenting {stem}")
  data     <- read_aniframe(parquet)
  metadata <- get_metadata(data)
  start_dt <- get_metadata(data, "start_datetime")

  sr <- derive_sampling_rate(data$time)
  cli::cli_alert_info("Sampling rate: {round(sr, 3)} Hz")

  cli::cli_alert_info("Cleaning + featurising...")
  data <- clean_tracks(data, sampling_rate = sr)
  data <- calculate_features(data, sampling_rate = sr)

  # --- 1. Sleep vs wake (unsupervised: changepoints on the locus, then 2-means) -
  cli::cli_alert_info("Sleep/wake segmentation...")
  sleep_data <- data |>
    downsample(max(1, round(sr * cfg$sleep_downsample_secs))) |>
    mutate(
      cp_sleep = detect_changepoints(
        weighted_centroid_distance_r, straightness_r, straightness,
        penalty = cfg$sleep_penalty
      ),
      segment_sleep = cumsum(cp_sleep)
    )

  sleep_clusters <- sleep_data |>
    group_by(segment_sleep) |>
    summarise(
      p95_pc1    = quantile(weighted_centroid_distance_r, 0.95, na.rm = TRUE, names = FALSE),
      max_pc1    = max(weighted_centroid_distance_r, na.rm = TRUE),
      pct_active = mean(weighted_centroid_distance_r > 1, na.rm = TRUE),
      sd_pc1     = sd(weighted_centroid_distance_r, na.rm = TRUE),
      .groups    = "drop"
    ) |>
    cluster_segments(num_clusters = 2, id_col = segment_sleep)

  sleep_data <- sleep_data |>
    label_segments(
      sleep_clusters,
      segment_id = segment_sleep,
      label_col  = "sleep_state",
      labels     = c("Sleep", "Awake")
    ) |>
    as_aniframe() |>
    set_metadata(metadata = metadata) |>
    set_metadata(variables_event = list(state = c("sleep_state"), point = as.character()))

  sleep_events <- sleep_data |>
    to_anievent() |>
    select(-any_of(c("track", "keypoint")))

  # --- 2. Active bouts within the longest Sleep segment ----------------------
  longest_segment <- sleep_events |>
    filter(label == "Sleep") |>
    slice_max(stop - start, n = 1)

  if (nrow(longest_segment) == 0) {
    cli::cli_alert_warning("{stem}: no Sleep segment found; writing sleep/wake only.")
    dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
    readr::write_csv(as_tibble(sleep_events), sw_out)
    next
  }

  cli::cli_alert_info("Detecting active bouts...")
  sleep_only <- data |>
    filter(between(time, longest_segment$start, longest_segment$stop)) |>
    mutate(intensity_max_r_power = motion_power(intensity_max_r, sampling_rate = sr)) |>
    mutate(intensity_max_r_power = filter_lowpass(intensity_max_r_power, cutoff_freq = 0.5, sampling_rate = sr)) |>
    mutate(
      # Detection signal = rolling SD of the raw motion-colour intensity (2 s window):
      # the level-blind variability signal that scored best in the notebook.
      detection_sd = rolling_sd(intensity_max_r, round(sr * 2)),
      bout_rem = find_bouts(
        detection_sd,
        method     = "double",
        k_hi       = cfg$bout_k_hi,
        k_lo       = cfg$bout_k_lo,
        min_length = round(sr * cfg$bout_min_length_secs),
        min_gap    = round(sr * cfg$bout_min_gap_secs)
      )
    )

  active <- sleep_only |>
    as_tibble() |>
    filter(!is.na(bout_rem)) |>
    transmute(
      bout_uid = paste(stem, bout_rem, sep = "#"),
      recording = stem,
      time,
      intensity_max_r_power,
      weighted_var_x_r, weighted_var_y_r, weighted_cov_yx_r,
      weighted_centroid_distance_r, weighted_centroid_distance_g, weighted_centroid_distance_b,
      colour_shift_rg, colour_shift_gb,
      straightness_r
    )

  if (nrow(active) == 0) {
    cli::cli_alert_warning("{stem}: no active bouts detected; writing sleep/wake only.")
    dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
    readr::write_csv(as_tibble(sleep_events), sw_out)
    next
  }

  # --- 3. Per-bout features + classification ---------------------------------
  cli::cli_alert_info("Classifying bouts...")
  bout_features <- compact_bout_features(active, id_col = "bout_uid",
                                         sampling_rate = sr,
                                         power_col = "intensity_max_r_power")

  bout_summary <- active |>
    group_by(recording, bout_uid) |>
    summarise(
      onset_s    = min(time),
      offset_s   = max(time),
      dur_secs   = n() / sr,
      peak_power = max(intensity_max_r_power, na.rm = TRUE),
      mean_power = mean(intensity_max_r_power, na.rm = TRUE),
      .groups    = "drop"
    ) |>
    mutate(
      start_datetime = start_dt,
      onset_datetime = start_dt + onset_s
    )

  state_pred <- classify_states(bout_features, classifier, bout_summary)

  # Final state with a reject band: confidently-Awake, confidently-REM, else
  # "uncertain" (the micro-movement ~ REM gray zone), per config.yaml.
  bout_states <- bout_summary |>
    left_join(select(state_pred, bout_uid, .pred_Awake), by = "bout_uid") |>
    left_join(bout_features, by = "bout_uid") |>
    mutate(
      final_state = case_when(
        .pred_Awake >= thr_cut + reject ~ "Awake",
        .pred_Awake <= thr_cut - reject ~ "REM",
        TRUE                            ~ "uncertain"
      )
    ) |>
    relocate(recording, bout_uid, onset_s, offset_s, dur_secs, final_state, .pred_Awake)

  cli::cli_alert_info("States: {paste(names(table(bout_states$final_state)), table(bout_states$final_state), sep='=', collapse=', ')}")

  # --- 4. Write artefacts ----------------------------------------------------
  dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
  readr::write_csv(as_tibble(sleep_events), sw_out)
  readr::write_csv(bout_states, bouts_out)
  cli::cli_alert_success("Wrote {.file {sw_out}} and {.file {bouts_out}}")
}
