# Changepoint detection for segmenting a (multivariate) signal.

# Flag changepoints across one or more equal-length numeric columns (passed via
# ...), treated as one multivariate signal. Returns a logical vector, TRUE at
# each segment boundary, so cumsum() gives a segment id. A single column takes
# the fast pure-C changepoint::PELT path; >=2 columns use fastcpd.
detect_changepoints <- function(..., method = "mean", penalty = 700) {
  # fastcpd needs a finite, gap-free series. Treat any non-finite value (incl. Inf,
  # which turns the covariance NaN and trips LAPACK) as missing, then interpolate.
  fill <- function(v) { v[!is.finite(v)] <- NA; aniprocess::replace_na(v, method = "linear") }
  data <- do.call(cbind, lapply(list(...), fill))
  n <- nrow(data)
  if (!all(is.finite(data))) stop("detect_changepoints(): non-finite values remain (e.g. NAs/Inf at the series ends) - fix those columns first.")

  if (ncol(data) == 1L && method %in% c("mean", "meanvariance")) {
    if (sd(data[, 1]) == 0) return(logical(n))   # constant series has no changes

    # cpt.mean segments on the raw scale while fastcpd normalises by variance.
    # Standardise to unit variance so `penalty` means the same across both engines;
    # scaling is monotone in the cost and never moves the changepoints.
    x <- as.numeric(scale(data[, 1]))
    model_fn <- if (method == "mean") tidychangepoint::fit_meanshift_norm else tidychangepoint::fit_meanvar
    fit <- tidychangepoint::segment(
      x, method = "pelt", model_fn = model_fn,
      penalty = "Manual", pen.value = penalty * log(n)   # == beta in fastcpd
    )
    cp <- tidychangepoint::changepoints(fit)
  } else if (method == "mean") {
    cp <- fastcpd::fastcpd.mean(data, beta = penalty * log(n), cp_only = TRUE)@cp_set
  } else if (method == "meanvariance") {
    cp <- fastcpd::fastcpd.meanvariance(data, beta = penalty * log(n), cp_only = TRUE)@cp_set
  } else if (method == "variance") {
    cp <- fastcpd::fastcpd.var(data, beta = penalty * log(n), cp_only = TRUE)@cp_set
  }

  # Both engines report a changepoint as the last index of the preceding segment,
  # so the boundary convention (and downstream cumsum) is identical.
  boundaries <- logical(n)
  boundaries[cp] <- TRUE
  boundaries
}
