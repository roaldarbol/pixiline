# Track cleaning + feature calculation.
# Extracted verbatim from segmentation.qmd (chunks `def-clean-tracks` and
# `def-calculate-features`) so the reusable pipeline featurises a new recording
# exactly as the research analysis / model training did. Keep these in sync if
# the notebook versions change.

# Tidy the raw tracks: drop low-confidence points, interpolate short gaps,
# Savitzky-Golay smooth. `process_vars` are the columns carried downstream.
clean_tracks <- function(aniframe, threshold = 0.6, sampling_rate = 30) {

  process_vars <- c(
    "x", "y", "bbox_area", "area", "eccentricity",
    "intensity_max_r", "intensity_max_g", "intensity_max_b", "intensity_max_lum",
    "intensity_mean_r", "intensity_mean_g", "intensity_mean_b", "intensity_mean_lum",
    "intensity_std_r", "intensity_std_g", "intensity_std_b", "intensity_std_lum",
    "weighted_centroid_x_r", "weighted_centroid_y_r", "weighted_var_x_r", "weighted_var_y_r", "weighted_cov_yx_r",
    "weighted_centroid_x_g", "weighted_centroid_y_g", "weighted_var_x_g", "weighted_var_y_g", "weighted_cov_yx_g",
    "weighted_centroid_x_b", "weighted_centroid_y_b", "weighted_var_x_b", "weighted_var_y_b", "weighted_cov_yx_b",
    "weighted_centroid_x_lum", "weighted_centroid_y_lum", "weighted_var_x_lum", "weighted_var_y_lum", "weighted_cov_yx_lum"
  )

  # Not smoothed: raw intensity means (for flicker analysis) and the variances
  # (SG can push them negative, breaking the later sqrt -> SD conversion).
  no_smooth <- c(
    "intensity_mean_r", "intensity_mean_g", "intensity_mean_b",
    grep("^weighted_var_", process_vars, value = TRUE)
  )

  aniframe <- aniframe |>
    filter_na_excursion() |>
    mutate(
      across(
        c(x, y),
        ~ if_else(confidence < threshold, NA_real_, .)
      )
    ) |>
    # Ensure that unreliable observations also return NA in the other variables.
    mutate(
      across(
        all_of(process_vars),
        ~ if_else(is.na(x), NA_real_, .)
      )
    ) |>
    # Interpolate missing values with a Stine interpolation (up to 5 s = 150 frames at 30 fps).
    mutate(
      across(
        all_of(process_vars),
        ~ replace_na_stine(., max_gap = sampling_rate * 5)
      )
    ) |>
    # Smooth with a Savitzky-Golay filter (1 s window = 30 frames at 30 fps).
    mutate(
      across(
        all_of(setdiff(process_vars, no_smooth)),
        ~ filter_sgolay(., sampling_rate = sampling_rate)
      )
    )

  aniframe
}

# Derive the kinematic + colour-locus features the segmentation/classification
# rely on (egocentric colour centroids, size-normalised spread, motion power...).
calculate_features <- function(aniframe, sampling_rate = 30) {
  aniframe <- aniframe |>
    calculate_kinematics() |>
    calculate_tortuosity()

  colour_centroid_y_vars <- c("weighted_centroid_y_r", "weighted_centroid_y_g", "weighted_centroid_y_b")
  colour_centroid_x_vars <- c("weighted_centroid_x_r", "weighted_centroid_x_g", "weighted_centroid_x_b")

  aniframe <- aniframe |>
    mutate(
      x_ego = 0,
      y_ego = 0
    ) |>
    mutate(
      across(
        all_of(colour_centroid_y_vars),
        ~ get_metadata(aniframe, "y_height") - .
        )
    ) |>
    # Make the colour centroids egocentric (relative to the animal's position).
    mutate(
      across(
        all_of(colour_centroid_y_vars),
        ~ . - .data$y
      )
    ) |>
    mutate(
      across(
        all_of(colour_centroid_x_vars),
        ~ . - .data$x
      )
    ) |>
    # Rolling straightness of the red motion-locus path.
    mutate(
      straightness_r = rolling_straightness(weighted_centroid_x_r, weighted_centroid_y_r, window = sampling_rate)
    ) |>
    # Normalise egocentric coordinates by blob size (semi-major axis).
    mutate(
      across(
        all_of(c(colour_centroid_x_vars, colour_centroid_y_vars)),
        ~ if_else(axis_major_length > 0, . / (axis_major_length / 2), NA_real_)
      )
    ) |>
    # Weighted variances -> SDs, on the same (fraction-of-semi-major-axis) scale.
    mutate(
        across(
          c("weighted_var_x_r", "weighted_var_y_r",
            "weighted_var_x_g", "weighted_var_y_g",
            "weighted_var_x_b", "weighted_var_y_b"),
          ~ if_else(axis_major_length > 0, sqrt(.) / (axis_major_length / 2), NA_real_)
        )
    ) |>
    # Locus displacement from body centre + inter-channel shift vectors.
    mutate(
      weighted_centroid_distance_r = sqrt(weighted_centroid_x_r^2 + weighted_centroid_y_r^2),
      weighted_centroid_distance_g = sqrt(weighted_centroid_x_g^2 + weighted_centroid_y_g^2),
      weighted_centroid_distance_b = sqrt(weighted_centroid_x_b^2 + weighted_centroid_y_b^2),
      colour_shift_rg = sqrt((weighted_centroid_x_g - weighted_centroid_x_r)^2 + (weighted_centroid_y_g - weighted_centroid_y_r)^2),
      colour_shift_gb = sqrt((weighted_centroid_x_b - weighted_centroid_x_g)^2 + (weighted_centroid_y_b - weighted_centroid_y_g)^2)
    ) |>
    # High-frequency motion power per channel (EMG-style envelope).
    mutate(
      across(
        c(intensity_mean_r, intensity_mean_g, intensity_mean_b),
        ~ motion_power(., sampling_rate = sampling_rate),
        .names = "{.col}_power"
      )
    )

  aniframe
}
