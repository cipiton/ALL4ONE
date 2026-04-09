# Recap Production

Shared-engine skill for multi-step recap production, asset preparation, and downstream episode scene planning.

## Execution Mode

- strategy: `step_prompt`
- startup: `metadata.startup.mode = explicit_step_selection`
- review flow: `metadata.execution.mode = sequential_with_review`
- input: single `.txt` file or non-recursive folder of `.txt` files
- outputs: `outputs/recap_production/{input_name}__{timestamp}/...`
- resume: enabled for interrupted runs

## Shared Review Flow

From the chosen step, the shared runtime now:

- generates the current step draft
- previews it in the terminal
- allows `Accept`, `Improve`, `Restart`, `View full`, or `Cancel`
- saves only accepted outputs
- continues to the next parsed step after acceptance until the workflow ends or the user cancels

## Steps

- step 1: `01_recap_script.txt`
- step 2: `02_assets.txt`
- step 3: `03_image_config.txt`
- step 4: `04_episode_scene_script.md` plus `04_episode_scene_script.json`

## Runtime Inputs

- `episode_count` on step 1 when the input is not a rewrite task
- `style` on the asset-extraction step

## References

- `references/step1-prompt.md`
- `references/step2-prompt.md`
- `references/step3-prompt.md`
- `references/step4-prompt.md`
