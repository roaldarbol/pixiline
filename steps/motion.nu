# Step: motion-colour video (BehaveAI).
# Step contract:  --stem <stem>  --output <base>  --input <path>  [--overwrite]
# Writes <base>/<stem>/videos/motion/<stem>_motion.mp4. Settings: config.yaml [motion].

def main [
    --stem: string             # recording id (required)
    --output: string           # output base dir (required)
    --input: string            # source video (required - this step's external input)
    --overwrite                # accepted for the uniform contract (motion always rewrites)
] {
    let project_root = $env.CURRENT_FILE | path dirname | path join ".."
    if $output == null { error make { msg: "motion: --output <base> is required" } }
    if $stem == null { error make { msg: "motion: --stem <name> is required" } }
    if $input == null { error make { msg: "motion: --input <path> is required" } }
    let cfg = open ($project_root | path join "config.yaml")
    let motion_out = $output | path join $stem "videos" "motion"
    mkdir $motion_out
    behaveai motion $input $motion_out --lum-weight $cfg.motion.lum_weight
}
