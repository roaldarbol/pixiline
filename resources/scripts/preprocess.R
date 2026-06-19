#!/usr/bin/env Rscript
# Step 4 - turn an Octron tracking export into a processed aniframe parquet.
#
# Normally driven through its wrapper (steps/preprocess.nu), which supplies the
# uniform step contract:
#   Rscript preprocess.R <base> --stem <stem> --input <video> [--overwrite]
#
# For the recording under <base>/<stem>/ with a single-individual Octron csv in
# tracking/raw/<stem>_bytetrack/, we read it with read_octron() and write
# tracking/processed/<stem>.parquet. Octron numbers frames by index and omits
# frames with no detection, so each row is mapped to its real time *by frame
# index*, not by position.
#
# Frame -> time: the source video's average frame rate is probed with ffprobe and
# time = frame_index / fps; start_datetime is taken from the video file's mtime.

suppressPackageStartupMessages({
  library(animovement)
  library(dplyr)
})

script_dir   <- dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[1]))
project_root <- normalizePath(file.path(script_dir, "..", ".."))   # resources/scripts -> root

# Pull a named "--flag value" out of the args, returning the value (or NA).
arg_value <- function(args, flag) {
  i <- match(flag, args)
  if (!is.na(i) && i < length(args)) args[i + 1] else NA_character_
}

args      <- commandArgs(trailingOnly = TRUE)
overwrite <- "--overwrite" %in% args
# --stem restricts processing to a single recording's folder; --input is the
# source video whose frame rate is probed for the frame -> time mapping.
stem_filter <- arg_value(args, "--stem")
video_arg   <- arg_value(args, "--input")
# Positional args are everything that is neither a --flag nor a flag's value.
flag_idx    <- which(args %in% c("--stem", "--input"))
drop_idx    <- sort(unique(c(flag_idx, flag_idx + 1)))
positional  <- args[setdiff(seq_along(args), drop_idx)]
positional  <- positional[!startsWith(positional, "--")]
base_dir    <- if (length(positional) >= 1) positional[[1]] else file.path(project_root, "output")

# Average frame rate of a video, via ffprobe (ships with the ffmpeg dependency).
probe_fps <- function(video) {
  rate <- tryCatch(
    system2("ffprobe", c("-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=avg_frame_rate",
                         "-of", "default=noprint_wrappers=1:nokey=1", shQuote(video)),
            stdout = TRUE, stderr = NULL),
    error = function(e) character(0)
  )
  rate <- trimws(rate[nzchar(rate)])
  if (!length(rate)) return(NA_real_)
  parts <- as.numeric(strsplit(rate[1], "/", fixed = TRUE)[[1]])
  fps <- if (length(parts) == 2 && parts[2] != 0) parts[1] / parts[2] else parts[1]
  if (is.finite(fps) && fps > 0) fps else NA_real_
}

stems <- basename(list.dirs(base_dir, recursive = FALSE))
if (!is.na(stem_filter)) stems <- stems[stems == stem_filter]

for (stem in stems) {
  raw_dir <- file.path(base_dir, stem, "tracking", "raw")
  if (!dir.exists(raw_dir)) {
    cli::cli_inform("Skipping {stem}: no tracking/raw/ folder.")
    next
  }

  pred_dirs <- list.dirs(raw_dir, recursive = FALSE)
  csv_files <- list.files(pred_dirs, pattern = "\\.csv$", full.names = TRUE)
  if (length(csv_files) != 1) {
    cli::cli_inform("Skipping {stem}: found {length(csv_files)} csv files (expected 1).")
    next
  }

  out_dir  <- file.path(base_dir, stem, "tracking", "processed")
  out_file <- file.path(out_dir, paste0(stem, ".parquet"))
  if (!overwrite && file.exists(out_file)) {
    cli::cli_inform("Skipping {stem}: already processed (use --overwrite to rebuild).")
    next
  }

  if (is.na(video_arg) || !file.exists(video_arg)) {
    cli::cli_abort(c(
      "{stem}: need the source video to probe the frame rate.",
      "x" = "pass --input <path> (the step wrapper does this automatically)."
    ))
  }
  fps <- probe_fps(video_arg)
  if (is.na(fps)) {
    cli::cli_abort(c(
      "{stem}: could not determine a frame rate.",
      "x" = "ffprobe failed on {.file {video_arg}}."
    ))
  }

  cli::cli_inform("Processing {stem} -> tracking/processed/{stem}.parquet ...")
  cli::cli_alert_info("Frame rate {round(fps, 3)} fps probed from {.file {basename(video_arg)}}.")
  data <- read_octron(csv_files)
  start <- as.POSIXct(file.mtime(video_arg))
  data <- data |>
    mutate(time = time / fps) |>
    as_aniframe() |>
    set_metadata(unit_time = "s", start_datetime = start)

  dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
  write_aniframe(data, out_file)
}
