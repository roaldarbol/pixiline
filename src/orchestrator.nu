# Generic pipeline orchestrator - runs the chain for ONE recording.
#
# It is not specific to any pipeline: it reads the ordered `steps:` list from
# config.yaml and runs each selected step with the uniform contract
#
#     <step>  --stem <stem>  --output <base>  [--input <path>]  [--overwrite]
#
# `--input` is passed only to steps that declare an external need (a `needs:`
# pattern without `{stem}`). Every step is per-recording and independent, so there
# is no batching - call this once per recording. Edit the pipeline in config.yaml,
# not here.
#
#   pixi run process clip.mp4 --output out
#   pixi run process clip.mp4 --output out --steps export,preprocess,segment
#   pixi run process --stem clip --output out --steps segment   # resume, no video

def main [
    input?: string             # source video (needed by steps with an external need)
    --output: string           # output base dir (required)
    --stem: string             # recording id (default: the input file's stem)
    --steps: string = ""       # comma-separated step names to run (default: all)
    --overwrite                # re-run steps even if their outputs exist
] {
    if $output == null { error make { msg: "--output <base> is required" } }
    let root = $env.CURRENT_FILE | path dirname | path join ".."
    let spec = open ($root | path join "config.yaml")
    let all = ($spec.steps? | default [])
    if ($all | is-empty) { print "No steps defined in config.yaml (`steps:`)."; return }

    let stem = if $stem != null {
        $stem
    } else if $input != null {
        $input | path parse | get stem
    } else {
        error make { msg: "pass a source video or --stem <name>" }
    }

    let want = if ($steps | is-empty) {
        $all | get name
    } else {
        $steps | split row "," | each { |s| $s | str trim } | where { |s| $s != "" }
    }
    let selected = $all | where { |s| $s.name in $want }
    if ($selected | is-empty) { print "No matching steps selected."; return }

    print $"Stem: ($stem)   Output: ($output)"
    print $"Steps: ($selected | get name | str join ' -> ')"

    for step in $selected {
        let needs_input = ($step.needs | any { |n| not ($n | str contains "{stem}") })
        print $"--- ($step.name) ---"
        mut args = [--stem $stem --output $output]
        if $needs_input {
            if $input == null {
                error make { msg: $"step '($step.name)' needs an input file; pass it as the first argument" }
            }
            $args = ($args | append [--input $input])
        }
        if $overwrite { $args = ($args | append "--overwrite") }
        ^pixi run -e $step.env $step.name -- ...$args
    }
    print "=== Done ==="
}
