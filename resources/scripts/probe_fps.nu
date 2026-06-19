# FPS-probe fallback. When a recording has no per-frame timestamp file in
# data/timestamps, preprocess.R needs a frame rate to convert frame index ->
# seconds. This reads the average frame rate straight from the video with
# ffprobe and prints it as a plain number.
#
#   pixi run probe-fps data/videos/clip.mp4      # -> 30.0
#
# preprocess.R calls the same ffprobe command internally, so you rarely need to
# run this by hand - it is here for inspection / the future GUI.

def main [
    video: string              # path to a video file
] {
    let rate = (
        ^ffprobe -v error -select_streams v:0
            -show_entries stream=avg_frame_rate
            -of default=noprint_wrappers=1:nokey=1 $video
        | str trim
    )
    # ffprobe reports the rate as a fraction like "30000/1001"; evaluate it.
    let parts = $rate | split row "/"
    let fps = if ($parts | length) == 2 {
        ($parts | first | into float) / ($parts | last | into float)
    } else {
        $rate | into float
    }
    print $fps
}
