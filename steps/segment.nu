# Step wrapper - conforms to the step contract and calls segment.R.
# Step contract:  --stem <stem>  --output <base>  [--overwrite]
# Translates to: Rscript segment.R <base> --stem <stem> [--overwrite]
# (segment.R derives the sampling rate from the parquet itself, so no --video).

def main [
    --stem: string             # recording id (required)
    --output: string           # output base dir (required)
    --overwrite
] {
    let project_root = $env.CURRENT_FILE | path dirname | path join ".."
    if $output == null { error make { msg: "segment: --output <base> is required" } }
    if $stem == null { error make { msg: "segment: --stem <name> is required" } }
    mut args = [($project_root | path join "resources/scripts/segment.R") $output --stem $stem]
    if $overwrite { $args = ($args | append "--overwrite") }
    Rscript ...$args
}
