# Per-segment featurisation and tidyclust clustering of segments/bouts.

# Extract per-segment time-series features (theft / catch22) from one or more
# channels. Returns one row per segment, columns <channel>_<feature>. Segments
# too short (< min_length) or zero-variance are dropped (catch22 can't handle
# them). `on` is tidy-select; each channel is featurised independently and joined.
extract_segment_features <- function(data,
                                     on,
                                     segment_id = segment_id,
                                     time = time,
                                     feature_set = "catch22",
                                     min_length = 24L,
                                     ...) {
  seg_q  <- rlang::enquo(segment_id)
  time_q <- rlang::enquo(time)
  on_q   <- rlang::enquo(on)

  seg_name  <- rlang::as_name(seg_q)
  time_name <- rlang::as_name(time_q)

  cols <- tidyselect::eval_select(on_q, data)
  if (length(cols) == 0) cli::cli_abort("{.arg on} matched no columns in {.arg data}.")
  channels <- names(cols)

  data <- dplyr::ungroup(data)

  per_channel <- lapply(channels, function(ch) {
    seg_sym <- rlang::sym(seg_name)
    d <- data |>
      dplyr::select(dplyr::all_of(c(seg_name, time_name, ch))) |>
      dplyr::filter(is.finite(.data[[ch]])) |>
      dplyr::group_by(!!seg_sym) |>
      dplyr::filter(dplyr::n() >= min_length, stats::sd(.data[[ch]]) > 0) |>
      dplyr::ungroup()

    if (nrow(d) == 0L) {
      cli::cli_warn("No segments of {.arg {ch}} are long enough (>= {min_length} finite, non-constant obs).")
      return(NULL)
    }

    ts <- tsibble::as_tsibble(d, key = !!seg_sym, index = !!rlang::sym(time_name))
    feats <- theft::calculate_features(ts, feature_set = feature_set, ...)

    feats |>
      dplyr::select("id", "names", "values") |>
      tidyr::pivot_wider(names_from = "names", values_from = "values", names_prefix = paste0(ch, "_"))
  })

  per_channel <- per_channel[!vapply(per_channel, is.null, logical(1))]
  if (length(per_channel) == 0L) cli::cli_abort("No channel had any usable segments after filtering.")

  Reduce(\(a, b) dplyr::full_join(a, b, by = "id"), per_channel) |>
    dplyr::rename(!!seg_name := "id") |>
    tibble::as_tibble()
}

# Per-cluster descriptive summary for the active-bout clusters: size, duration,
# power, dominant annotation label, and time-of-day concentration. `tod_col` is
# hours-of-day in [0,24); conc_R is the circular resultant length (0 = spread
# over the day, 1 = all at one time) and rayleigh_p its approximate significance.
cluster_summaries <- function(bouts, cluster_col = "cluster",
                              tod_col = "tod_hours", truth_col = "truth") {
  bouts |>
    dplyr::mutate(.ang = 2 * pi * .data[[tod_col]] / 24) |>
    dplyr::group_by(dplyr::across(dplyr::all_of(cluster_col))) |>
    dplyr::summarise(
      n              = dplyr::n(),
      median_dur_s   = stats::median(dur_secs),
      median_peak    = stats::median(peak_power),
      median_mean    = stats::median(mean_power),
      dominant_label = { t <- table(.data[[truth_col]]); if (length(t)) names(t)[which.max(t)] else NA_character_ },
      pct_rem        = mean(.data[[truth_col]] == "REM", na.rm = TRUE),
      mean_hour      = (atan2(mean(sin(.ang)), mean(cos(.ang))) %% (2 * pi)) * 24 / (2 * pi),
      conc_R         = sqrt(mean(cos(.ang))^2 + mean(sin(.ang))^2),
      rayleigh_p     = exp(-dplyr::n() * (mean(cos(.ang))^2 + mean(sin(.ang))^2)),
      .groups = "drop"
    )
}

# Compact, interpretable per-bout features mapping to the three behaviour axes
# (Roessler): movement LEVEL (power), spatial SPREAD (var/cov of the motion
# locus: localized twitch vs whole-body), and TEMPORAL pattern (sporadic vs
# persistent), plus duration. ~10 features (vs ~200 catch22), so easier to reason
# about and less overfit-prone with few labelled bouts. Used identically at fit
# and predict time. Needs the columns carried in the active_bouts accumulation.
compact_bout_features <- function(data, id_col = "bout_uid", sampling_rate = 30,
                                  power_col = "intensity_max_r_power") {
  ac1 <- function(x) {                                   # lag-1 autocorrelation = persistence
    x <- x[is.finite(x)]
    if (length(x) < 3L || stats::sd(x) == 0) return(NA_real_)
    stats::acf(x, lag.max = 1, plot = FALSE)$acf[2]
  }
  data |>
    dplyr::group_by(dplyr::across(dplyr::all_of(id_col))) |>
    dplyr::summarise(
      duration       = dplyr::n() / sampling_rate,
      # LEVEL
      peak_power     = max(.data[[power_col]], na.rm = TRUE),
      mean_power     = mean(.data[[power_col]], na.rm = TRUE),
      # TEMPORAL: burstiness (CV) and persistence (lag-1 autocorrelation) of power
      power_cv       = stats::sd(.data[[power_col]], na.rm = TRUE) /
                         (mean(.data[[power_col]], na.rm = TRUE) + 1e-9),
      power_autocorr = ac1(.data[[power_col]]),
      # SPREAD: how spatially spread the motion locus is (localized vs whole-body)
      spread_var     = mean(weighted_var_x_r + weighted_var_y_r, na.rm = TRUE),
      spread_cov     = mean(abs(weighted_cov_yx_r), na.rm = TRUE),
      # locus geometry
      locus_dist     = mean(weighted_centroid_distance_r, na.rm = TRUE),
      straightness   = mean(straightness_r, na.rm = TRUE),
      colour_shift_rg   = mean(colour_shift_rg, na.rm = TRUE),
      colour_shift_gb   = mean(colour_shift_gb, na.rm = TRUE),
      .groups = "drop"
    )
}

# Full per-bout feature table for the active-bout clustering: catch22 features on
# each `channels` column, plus duration and power summaries from `power_col`.
# Used identically at fit time and when scoring new bouts, so the train/predict
# feature columns always match. `id_col`/`time_col` are column-name strings.
active_bout_features <- function(data, channels,
                                 power_col = "intensity_max_r_power",
                                 id_col = "bout_uid", time_col = "time",
                                 sampling_rate = 30, feature_set = "catch22") {
  ts <- extract_segment_features(
    data, on = dplyr::all_of(channels),
    segment_id = !!rlang::sym(id_col), time = !!rlang::sym(time_col),
    feature_set = feature_set
  )
  simple <- data |>
    dplyr::group_by(dplyr::across(dplyr::all_of(id_col))) |>
    dplyr::summarise(
      dur_secs   = dplyr::n() / sampling_rate,
      peak_power = max(.data[[power_col]], na.rm = TRUE),
      mean_power = mean(.data[[power_col]], na.rm = TRUE),
      .groups = "drop"
    )
  dplyr::left_join(ts, simple, by = id_col)
}

# Score new active bouts with a saved clustering workflow. Rebuilds the compact
# features (same recipe travels inside `model`), then predicts the cluster.
# Returns one row per bout: `id_col` and `.pred_cluster`.
assign_clusters <- function(new_data, model,
                            power_col = "intensity_max_r_power",
                            id_col = "bout_uid", sampling_rate = 30) {
  feats <- compact_bout_features(new_data, id_col = id_col,
                                 sampling_rate = sampling_rate, power_col = power_col)
  dplyr::bind_cols(
    dplyr::select(feats, dplyr::all_of(id_col)),
    stats::predict(model, feats)
  )
}

# The exact feature matrix the clustering saw: the fitted recipe applied to
# `features`, giving one row per bout (the `id_col` plus the processed predictors,
# PCA components if pca_threshold was set). For UMAP / hclust / PERMANOVA so they
# operate in the same space as the deployed k-means.
prepped_features <- function(workflow, features) {
  recipes::bake(workflows::extract_recipe(workflow), new_data = features)
}

# Cluster a per-segment feature table with tidyclust. Recipe treats `id_col` as
# an ID, drops zero-variance + >0.9-correlated predictors, normalises; then fits
# a k-means workflow. num_clusters = NULL tunes k over `k_range` by v-fold CV on
# average silhouette; an integer uses that k directly. `pca_threshold` (e.g. 0.9)
# adds a PCA step retaining that fraction of variance - recommended when there
# are many catch22 features relative to bouts (p approaching n), as it decorrelates
# and denoises before k-means; it travels in the workflow, so new data and any
# downstream embedding use the same reduced space. Returns the fitted workflow
# (recipe + model -> reusable on new data) plus assignments and tuning.
cluster_segments <- function(feat,
                             num_clusters = NULL,
                             id_col = segment_id,
                             k_range = 2:10,
                             v = 5,
                             seed = 1,
                             pca_threshold = NULL) {
  id_q    <- rlang::enquo(id_col)
  id_name <- rlang::as_name(id_q)

  # Impute before corr/normalize: catch22 leaves NAs for bouts where a channel was
  # flat/too short, and k-means can't fit on NAs. Median imputation is learned at
  # fit time and travels in the workflow, so new data is imputed consistently.
  rec <- recipes::recipe(~ ., data = feat) |>
    recipes::update_role(!!id_q, new_role = "id") |>
    recipes::step_zv(recipes::all_predictors()) |>
    recipes::step_impute_median(recipes::all_predictors()) |>
    recipes::step_corr(recipes::all_predictors(), threshold = 0.9) |>
    recipes::step_normalize(recipes::all_predictors())
  if (!is.null(pca_threshold)) {
    rec <- recipes::step_pca(rec, recipes::all_predictors(), threshold = pca_threshold)
  }

  # Too few segments to cluster (k-means needs more rows than centres): give each
  # its own cluster and skip the fit; the downstream labelling step renames them.
  n_seg <- nrow(feat)
  min_needed <- if (is.null(num_clusters)) min(k_range) else num_clusters
  if (n_seg <= min_needed) {
    assignments <- dplyr::bind_cols(
      dplyr::select(feat, dplyr::all_of(id_name)),
      tibble::tibble(.cluster = factor(paste0("Cluster_", seq_len(n_seg))))
    )
    return(list(workflow = NULL, recipe = rec, assignments = assignments,
                features = feat, tuning = NULL))
  }

  if (is.null(num_clusters)) {
    spec <- tidyclust::k_means(num_clusters = hardhat::tune()) |>
      parsnip::set_engine("stats")
    wf <- workflows::workflow() |>
      workflows::add_recipe(rec) |>
      workflows::add_model(spec)

    set.seed(seed)
    resamples <- rsample::vfold_cv(feat, v = v)
    grid <- tibble::tibble(num_clusters = as.integer(k_range))
    tuned <- tidyclust::tune_cluster(
      wf, resamples = resamples, grid = grid,
      metrics = tidyclust::cluster_metric_set(tidyclust::silhouette_avg)
    )
    best <- tune::select_best(tuned, metric = "silhouette_avg")
    fit <- parsnip::fit(tune::finalize_workflow(wf, best), feat)
    tuning <- list(results = tuned, best = best)
  } else {
    spec <- tidyclust::k_means(num_clusters = num_clusters) |>
      parsnip::set_engine("stats")
    wf <- workflows::workflow() |>
      workflows::add_recipe(rec) |>
      workflows::add_model(spec)
    fit <- parsnip::fit(wf, feat)
    tuning <- NULL
  }

  assignments <- dplyr::bind_cols(
    dplyr::select(feat, dplyr::all_of(id_name)),
    tidyclust::extract_cluster_assignment(fit)
  )

  list(workflow = fit, recipe = rec, assignments = assignments,
       features = feat, tuning = tuning)
}

# Join cluster labels back onto segmented data by segment_id (adds `label_col`).
# If `labels` is given, clusters are first renamed by activity: each cluster's
# mean z-scored feature level is ranked least->most active and `labels` applied
# in that order, so labels are consistent regardless of arbitrary cluster numbers.
label_segments <- function(data,
                           cluster_result,
                           segment_id = segment_id,
                           label_col = "cluster",
                           labels = NULL,
                           order_by = NULL) {
  id_q    <- rlang::enquo(segment_id)
  id_name <- rlang::as_name(id_q)

  asg <- cluster_result$assignments |>
    dplyr::select(dplyr::all_of(id_name), ".cluster")

  if (!is.null(labels)) {
    feats <- cluster_result$features
    activity_cols <- if (is.null(order_by)) {
      setdiff(names(feats)[vapply(feats, is.numeric, logical(1))], id_name)
    } else order_by

    # Per-segment activity = mean across z-scored features (z-scoring stops a
    # large-scale feature dominating), then averaged per cluster.
    activity <- tibble::tibble(
      !!id_name := feats[[id_name]],
      .activity = rowMeans(scale(as.matrix(feats[, activity_cols, drop = FALSE])), na.rm = TRUE)
    )
    ranked <- asg |>
      dplyr::left_join(activity, by = id_name) |>
      dplyr::group_by(.cluster) |>
      dplyr::summarise(.activity = mean(.activity, na.rm = TRUE), .groups = "drop") |>
      dplyr::arrange(.activity)                       # least -> most active

    if (length(labels) < nrow(ranked)) {
      stop("`labels` has fewer entries (", length(labels), ") than clusters (", nrow(ranked), ").")
    }
    if (length(labels) > nrow(ranked)) {
      warning("Only ", nrow(ranked), " cluster(s) for ", length(labels),
              " labels - assigning the least-active label(s).")
    }
    lut <- labels[seq_len(nrow(ranked))]
    names(lut) <- as.character(ranked$.cluster)
    asg <- dplyr::mutate(asg, .cluster = factor(lut[as.character(.cluster)], levels = labels))
  }

  asg <- dplyr::rename(asg, !!label_col := ".cluster")
  data |>
    dplyr::select(-dplyr::any_of(label_col)) |>
    dplyr::left_join(asg, by = id_name)
}
