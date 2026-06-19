# Step wrapper - conforms to the step contract and calls preprocess.R.
# Step contract:  --stem <stem>  --output <base>  --input <path>  [--overwrite]
# Translates to: Rscript preprocess.R <base> --stem <stem> --input <video> [--overwrite]
# (the R script needs the source video to probe its frame rate with ffprobe).

def main [
    --stem: string             # recording id (required)
    --output: string           # output base dir (required)
    --input: string            # source video (required - for the ffprobe frame rate)
    --overwrite
] {
    let project_root = $env.CURRENT_FILE | path dirname | path join ".."
    if $output == null { error make { msg: "preprocess: --output <base> is required" } }
    if $stem == null { error make { msg: "preprocess: --stem <name> is required" } }
    if $input == null { error make { msg: "preprocess: --input <path> is required" } }
    mut args = [($project_root | path join "resources/scripts/preprocess.R") $output --stem $stem --input $input]
    if $overwrite { $args = ($args | append "--overwrite") }
    Rscript ...$args
}
