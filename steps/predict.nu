# Step: Octron prediction / tracking with the Portia YOLO model.
# Step contract:  --stem <stem>  --output <base>  --input <path>  [--overwrite]
# Runs on the source video (see config.yaml `steps:` - predict needs *.mp4). Writes
# <base>/<stem>/tracking/raw/. Settings (model, batch size, flags): config.yaml [predict].

def main [
    --stem: string             # recording id (required)
    --output: string           # output base dir (required)
    --input: string            # source video (required - this step's external input)
    --overwrite                # accepted for the uniform contract (octron always overwrites)
] {
    let project_root = $env.CURRENT_FILE | path dirname | path join ".."
    if $output == null { error make { msg: "predict: --output <base> is required" } }
    if $stem == null { error make { msg: "predict: --stem <name> is required" } }
    if $input == null { error make { msg: "predict: --input <path> is required" } }
    let cfg = open ($project_root | path join "config.yaml")
    let model = $project_root | path join $cfg.predict.model
    let tracking_out = $output | path join $stem "tracking" "raw"
    mkdir $tracking_out

    mut flags = [
        --output-dir $tracking_out
        --model $model
        --overwrite
        --infer-batch-size $cfg.predict.infer_batch_size
    ]
    if $cfg.predict.detailed { $flags = ($flags | append "--detailed") }
    if $cfg.predict.one_object_per_label { $flags = ($flags | append "--one-object-per-label") }

    octron predict $input ...$flags
}
