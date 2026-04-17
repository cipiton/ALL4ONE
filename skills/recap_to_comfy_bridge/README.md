# Recap To Comfy Bridge

This ONE4ALL Skill 4 converts the Skill 2 `02_recap_production` bundle into stage-04 bridge outputs: canonical `assets.json`, legacy `videoarc_assets.json`, and `videoarc_storyboard.json`.

## What It Does

1. locates the source recap stage bundle
2. validates these required recap artifacts:
   - `04_episode_scene_script.json`
   - either `02_assets.json` or `02_assets.txt`
   - either `03_image_config.json` or `03_image_config.txt`
3. prefers the recap-production JSON sidecars when they exist and falls back to txt for old runs
4. optionally compiles stronger per-asset Z-Image prompts with Qwen through the configured `qwen` model alias
5. writes:
   - `assets.json`
   - `videoarc_assets.json`
   - `videoarc_storyboard.json`
   - `bridge_summary.json`

## Input

Preferred input:

- the Skill 2 `02_recap_production` stage folder

Allowed fallback:

- the file `02_recap_production/04_episode_scene_script.json`

The shared runtime resolves folder input to the stage's `04_episode_scene_script.json`, and the bridge then loads sibling recap files from that same `02_recap_production` folder.

Public contract:

- preferred: `outputs/stories/<story_slug>/<run_id>/02_recap_production/`
- fallback: `outputs/stories/<story_slug>/<run_id>/02_recap_production/04_episode_scene_script.json`
- story run root is supported only when the shared runtime can resolve it to `02_recap_production`
- do not pass `02_assets.json`, `03_image_config.json`, or bridge-stage `assets.json` as entry files

Legacy `01_recap_production` folders from earlier runs are still accepted.

The bridge resolves these files from the recap stage folder:

- required: `04_episode_scene_script.json`
- required with JSON-first fallback: `02_assets.json` preferred, else `02_assets.txt`
- required with JSON-first fallback: `03_image_config.json` preferred, else `03_image_config.txt`

## Output Layout

Within the story-first run folder, stage 04 creates:

```text
outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/
  assets.json
  videoarc_assets.json
  videoarc_storyboard.json
  bridge_summary.json
```

## Qwen Prompt Compiler

The bridge is still a normalization stage, but it can now call Qwen as a prompt compiler for downstream Z-Image asset generation. The compiler uses the configured `qwen` model alias, currently `qwen/3-32b`, and reads structured asset fields such as `style_preset`, `style_hint`, `style_lighting`, `core_feature`, `subject_content`, `description`, `role`, `personality_traits`, `prompt_fields`, and `source.raw_lines`.

When compilation succeeds, each asset entry in `assets.json` may include:

- `compiled_prompt`
- `compiled_prompt_model`
- `compiled_prompt_version`
- `compiled_prompt_source`
- `compiled_from_fields`
- `compiled_prompt_rationale` when the model returns a useful short note

The original normalized fields are preserved for compatibility. If Qwen is unavailable, the API key is missing, or a per-asset compile call fails, the bridge keeps the deterministic normalized fields and records the fallback in `bridge_summary.json` under `qwen_prompt_compiler`.

Set `ONE4ALL_QWEN_ASSET_PROMPT_COMPILER=0` to force the deterministic fallback path for bridge validation or offline runs.

## v1 Notes

- deterministic local conversion remains the fallback path
- Qwen prompt compilation is optional and does not change the bridge input/output file contract
- no ComfyUI calls yet
- no clip payload generation yet
- asset parsing is based mainly on `03_image_config.json` when present, with txt fallback for legacy recap runs
- storyboard shots preserve recap Step 4 beat metadata such as `priority`, `beat_role`, `pace_weight`, and `asset_focus`
