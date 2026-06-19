# Supervised classification of active bouts (Awake vs active-sleep/REM).

# Train an Awake-vs-REM classifier on the LABELLED bouts (those overlapping a
# scored Awake or REM event). Cross-validated leave-one-recording-out
# (group_vfold by `group`), since bouts within a recording are correlated and the
# model is deployed to new recordings - random folds would over-estimate. The
# fitted workflow (recipe + model) re-applies to any bout via predict().
#
# `data` is one row per bout: the compact features, the `outcome` factor
# (Awake/REM), the `id_col`, and the `group` (recording). `engine` is "glm"
# (default, interpretable, no extra dependency) or "ranger" (random forest, more
# robust to feature interactions / separation; needs the ranger package).
#
# Returns: the fitted `workflow`, `cv_metrics` (roc_auc / accuracy /
# bal_accuracy / f_meas, leave-one-recording-out), out-of-fold `cv_pred`, and -
# for glm - the `coefs` (which features drive the Awake call).
train_state_classifier <- function(data, id_col = "bout_uid", outcome = "truth",
                                   group = "recording",
                                   engine = c("ranger", "glm"), seed = 1) {
  engine <- match.arg(engine)
  data <- dplyr::mutate(data, dplyr::across(dplyr::all_of(outcome), factor))

  rec <- recipes::recipe(stats::as.formula(paste(outcome, "~ .")), data = data) |>
    recipes::update_role(dplyr::all_of(c(id_col, group)), new_role = "id") |>
    recipes::step_impute_median(recipes::all_numeric_predictors()) |>
    recipes::step_normalize(recipes::all_numeric_predictors())

  spec <- if (engine == "ranger") {
    if (!requireNamespace("ranger", quietly = TRUE)) {
      cli::cli_abort("engine = {.val ranger} needs the {.pkg ranger} package.")
    }
    parsnip::rand_forest(trees = 500) |>
      parsnip::set_engine("ranger", importance = "permutation") |>
      parsnip::set_mode("classification")
  } else {
    parsnip::logistic_reg() |>
      parsnip::set_engine("glm") |> parsnip::set_mode("classification")
  }

  wf <- workflows::workflow() |>
    workflows::add_recipe(rec) |>
    workflows::add_model(spec)

  set.seed(seed)
  folds <- rsample::group_vfold_cv(data, group = !!rlang::sym(group))
  mset  <- yardstick::metric_set(yardstick::roc_auc, yardstick::accuracy,
                                 yardstick::bal_accuracy, yardstick::f_meas)
  cv <- tune::fit_resamples(wf, folds, metrics = mset,
                            control = tune::control_resamples(save_pred = TRUE))

  fitted  <- parsnip::fit(wf, data)
  engine_fit <- workflows::extract_fit_engine(fitted)
  # Feature ranking: glm coefficients, or ranger permutation importance.
  importance <- if (engine == "ranger") {
    imp <- engine_fit$variable.importance
    tibble::tibble(term = names(imp), importance = as.numeric(imp)) |>
      dplyr::arrange(dplyr::desc(importance))
  } else {
    broom::tidy(engine_fit)
  }

  list(
    workflow   = fitted,
    cv_metrics = tune::collect_metrics(cv),
    cv_pred    = tune::collect_predictions(cv),
    importance = importance,
    coefs      = if (engine == "glm") importance else NULL
  )
}

# Benchmark several classification engines on the same leave-one-recording-out
# folds, to pick the best for this data rather than a priori. Engines whose
# package is absent are skipped with a note. Returns CV roc_auc / accuracy /
# bal_accuracy per engine (no tuning - a fair first pass at defaults).
compare_engines <- function(data, engines = c("glm", "glmnet", "ranger", "xgboost"),
                            id_col = "bout_uid", outcome = "truth",
                            group = "recording", seed = 1) {
  data <- dplyr::mutate(data, dplyr::across(dplyr::all_of(outcome), factor))
  rec <- recipes::recipe(stats::as.formula(paste(outcome, "~ .")), data = data) |>
    recipes::update_role(dplyr::all_of(c(id_col, group)), new_role = "id") |>
    recipes::step_impute_median(recipes::all_numeric_predictors()) |>
    recipes::step_normalize(recipes::all_numeric_predictors())

  pkg_for  <- c(glm = "stats", glmnet = "glmnet", ranger = "ranger",
                xgboost = "xgboost", svm = "kernlab")
  make_spec <- function(e) switch(e,
    glm     = parsnip::logistic_reg()                          |> parsnip::set_engine("glm"),
    glmnet  = parsnip::logistic_reg(penalty = 0.05, mixture = 0.5) |> parsnip::set_engine("glmnet"),
    ranger  = parsnip::rand_forest(trees = 500)               |> parsnip::set_engine("ranger"),
    xgboost = parsnip::boost_tree(trees = 500)                |> parsnip::set_engine("xgboost"),
    svm     = parsnip::svm_rbf()                              |> parsnip::set_engine("kernlab")
  )

  set.seed(seed)
  folds <- rsample::group_vfold_cv(data, group = !!rlang::sym(group))
  mset  <- yardstick::metric_set(yardstick::roc_auc, yardstick::accuracy,
                                 yardstick::bal_accuracy)
  dplyr::bind_rows(lapply(engines, function(e) {
    if (!requireNamespace(pkg_for[[e]], quietly = TRUE)) {
      cli::cli_alert_warning("Skipping {.val {e}}: install {.pkg {pkg_for[[e]]}}.")
      return(NULL)
    }
    wf <- workflows::workflow() |>
      workflows::add_recipe(rec) |>
      workflows::add_model(parsnip::set_mode(make_spec(e), "classification"))
    tune::fit_resamples(wf, folds, metrics = mset) |>
      tune::collect_metrics() |>
      dplyr::transmute(engine = e, .metric, mean, std_err, n)
  }))
}

# Tune the decision threshold from out-of-fold predictions. The default 0.5 cut
# leans toward the prevalent class; sweeping the cutoff and picking the one that
# maximises `optimize` (default balanced accuracy = Youden's J) rebalances the
# classes honestly (chosen on held-out predictions). `sensitivity` is recall of
# the event (first) level, `specificity` recall of the other. Returns the full
# threshold curve plus the best row.
tune_threshold <- function(cv_pred, truth = "truth", prob = NULL,
                           optimize = "bal_accuracy", by = 0.01) {
  ev <- levels(cv_pred[[truth]])[1]
  if (is.null(prob)) prob <- paste0(".pred_", ev)
  y <- cv_pred[[truth]] == ev
  p <- cv_pred[[prob]]
  curve <- dplyr::bind_rows(lapply(seq(0, 1, by = by), function(t) {
    pe <- p >= t
    tp <- sum(pe & y); fn <- sum(!pe & y); tn <- sum(!pe & !y); fp <- sum(pe & !y)
    sens <- if (tp + fn == 0) NA_real_ else tp / (tp + fn)
    spec <- if (tn + fp == 0) NA_real_ else tn / (tn + fp)
    tibble::tibble(threshold = t, sensitivity = sens, specificity = spec,
                   bal_accuracy = (sens + spec) / 2, youden = sens + spec - 1,
                   accuracy = (tp + tn) / length(y))
  }))
  list(curve = curve, best = curve[which.max(curve[[optimize]]), ], event = ev)
}

# Classify bouts with a trained state classifier. `features` is the compact
# per-bout feature table; `meta` supplies the id columns the recipe carries
# (bout_uid + recording). Returns one row per bout: id + `.pred_class` + class
# probabilities.
classify_states <- function(features, model, meta,
                            id_col = "bout_uid", group = "recording") {
  newdata <- dplyr::left_join(features,
                              dplyr::distinct(meta[c(id_col, group)]), by = id_col)
  dplyr::bind_cols(
    dplyr::select(newdata, dplyr::all_of(id_col)),
    stats::predict(model, newdata),
    stats::predict(model, newdata, type = "prob")
  )
}
