# OPTIONAL - tracklet-overlay video, for visual QC only (not part of `steps:`).
# Step contract:  --stem <stem>  --output <base>  [--overwrite]
# Reads the Octron predictions under <base>/<stem>/tracking/raw/ plus the motion
# video and writes to <base>/<stem>/videos/tracklets/. Settings: config.yaml [render].

def main [
    --stem: string             # recording id (required)
    --output: string           # output base dir (required)
    --overwrite                # accepted for the uniform contract (octron render rewrites)
] {
    let project_root = $env.CURRENT_FILE | path dirname | path join ".."
    if $output == null { error make { msg: "render: --output <base> is required" } }
    if $stem == null { error make { msg: "render: --stem <name> is required" } }
    let cfg = open ($project_root | path join "config.yaml")
    let raw_dir = $output | path join $stem "tracking" "raw"
    let predictions_path = ls $raw_dir | where type == dir | get name | first
    let motion_video = $output | path join $stem "videos" "motion" $"($stem)_motion.mp4"
    let video_out_dir = $output | path join $stem "videos" "tracklets"

    mut flags = [
        --video $motion_video
        --output $video_out_dir
        --tracklets
        --preset $cfg.render.preset
        --tracklet-interpolate $cfg.render.tracklet_interpolate
        --tracklet-size $cfg.render.tracklet_size
    ]
    if $cfg.render.tracklet_mask_centroids { $flags = ($flags | append "--tracklet-mask-centroids") }

    octron render $predictions_path ...$flags
}
