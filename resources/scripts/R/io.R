# Reading timestamps / per-recording I/O helpers.

# Per-frame timestamps as seconds since the first frame. Returns `seconds`
# (first element 0) and `start` (POSIXct of the first frame).
read_relative_timestamps <- function(path) {
  timestamps <- vroom::vroom(
    path,
    delim = ",", # single column, but vroom needs an explicit delimiter
    col_types = vroom::cols(Timestamp = vroom::col_datetime()),
    show_col_types = FALSE
  )[["Timestamp"]]
  list(
    seconds = as.numeric(difftime(timestamps, timestamps[1], units = "secs")),
    start = timestamps[1]
  )
}

# Raw (unparsed) Timestamp column. vroom indexes the file's line offsets but
# leaves the character values lazy, so this is cheap even for long recordings.
# Pair with frame_seconds() to parse only the rows you need.
read_timestamps_raw <- function(path) {
  vroom::vroom(
    path,
    delim = ",", # single column, but vroom needs an explicit delimiter
    col_types = vroom::cols(Timestamp = vroom::col_character()),
    show_col_types = FALSE
  )[["Timestamp"]]
}

# Elapsed seconds since the first frame for specific 0-based frame indices.
# `ts` is the raw character vector from read_timestamps_raw(); frame 0 is the
# first element. Only the reference frame and the requested frames are parsed,
# avoiding a full-file datetime parse + difftime.
frame_seconds <- function(ts, frames) {
  parsed <- readr::parse_datetime(ts[c(1L, frames + 1L)])
  as.numeric(difftime(parsed[-1], parsed[1], units = "secs"))
}
