# Recap To Comfy Bridge

This ONE4ALL skill converts a `recap_production` output bundle into VideoArc-style bridge payloads for legacy ComfyUI workflows.

## What It Does

1. locates the source recap run folder
2. validates these required recap artifacts:
   - `02_assets.txt`
   - `03_image_config.txt`
   - `04_episode_scene_script.json`
3. parses the current asset/config/scene-plan outputs
4. writes:
   - `videoarc_assets.json`
   - `videoarc_storyboard.json`
   - `bridge_summary.json`

## Input

Use either:

- a `recap_production` run folder
- or the file `04_episode_scene_script.json` inside that folder

The current bridge skill is configured to discover folder input through the top-level JSON file, so the recap output folder should contain that file directly at the top level.

## Output Layout

Within the normal ONE4ALL output root, the skill creates:

```text
outputs/
  recap_to_comfy_bridge/
    <run_name>__<timestamp>/
      videoarc_assets.json
      videoarc_storyboard.json
      bridge_summary.json
```

## v1 Notes

- deterministic local conversion only
- no ComfyUI calls yet
- no clip payload generation yet
- asset parsing is based mainly on `03_image_config.txt`, with `02_assets.txt` used for summary ordering and cross-checks
- storyboard shots preserve recap Step 4 beat metadata such as `priority`, `beat_role`, `pace_weight`, and `asset_focus`
