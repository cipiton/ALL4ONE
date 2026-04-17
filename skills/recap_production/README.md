# Recap Production

Shared-engine skill for multi-step recap production, asset preparation, and downstream episode scene planning.

## Execution Mode

- strategy: `step_prompt`
- startup: `metadata.startup.mode = explicit_step_selection`
- review flow: `metadata.execution.mode = sequential_with_review`
- input: single `.txt` file or non-recursive folder of `.txt` files
- outputs: story-first recap stage folder `outputs/stories/<story_slug>/<run_id>/01_recap_production/...`
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
- step 2: structured-first asset extraction, saved as canonical `02_assets.json` and rendered companion `02_assets.txt`
- step 3: structured-first image-config generation, saved as canonical `03_image_config.json` and rendered companion `03_image_config.txt`
- step 4: `04_episode_scene_script.md` plus `04_episode_scene_script.json`

Asset prompt defaults now target single clean assets for downstream generation:

- characters: one full-body identity reference, front-facing, neutral pose
- scenes: one coherent environment image
- props: one clean prop image

New recap prompt sources no longer ask for multi-view sheets or board-style prop layouts. The structured JSON renderer also strips legacy layout wording when old outputs are re-rendered.

## Runtime Inputs

- `episode_count` on step 1 when the input is not a rewrite task
- `style` on the asset-extraction step

## References

- `references/step1-prompt.md`
- `references/step2-prompt.md`
- `references/step3-prompt.md`
- `references/step4-prompt.md`
