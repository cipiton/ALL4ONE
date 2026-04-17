---
name: recap_to_keyscene_kontext
display_name: Recap To Keyscene Kontext
description: Generate recap keyscene I2I images by reading stage-04 storyboard data and stage-05 T2I assets, injecting beat-specific image references and prompts into a ComfyUI Flux Kontext API workflow JSON, submitting jobs to a running ComfyUI instance, and writing stage-06 outputs.
supports_resume: false
input_extensions:
  - .json
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "Recap To Keyscene Kontext"
      zh: "解说关键帧 Kontext"
    description:
      en: "Stage 06 keyscene I2I: combine recap storyboard beats with generated T2I assets through a ComfyUI Flux Kontext API workflow."
      zh: "第 06 阶段关键帧 I2I：将解说分镜 beat 与已生成 T2I 资产通过 ComfyUI Flux Kontext API 工作流合成为关键帧。"
    workflow_hint:
      en: "ComfyUI must already be running for live runs. Preferred input is the story run folder; the skill auto-resolves both `04_recap_to_comfy_bridge/` and `05_assets_t2i/`. Legacy `03_recap_to_comfy_bridge/` and `04_assets_t2i/` are still accepted for old runs."
      zh: "实时运行前需要先启动 ComfyUI。首选输入是故事运行目录；技能会自动解析 `04_recap_to_comfy_bridge/` 和 `05_assets_t2i/`。旧运行中的 `03_recap_to_comfy_bridge/` 与 `04_assets_t2i/` 仍兼容。"
    input_hint:
      en: "Preferred input: `outputs/stories/<story_slug>/<run_id>/`. Convenience fallbacks: `04_recap_to_comfy_bridge/`, `05_assets_t2i/`, an asset-group subfolder, or a file inside either stage; the runner resolves both required stages automatically."
      zh: "首选输入：`outputs/stories/<story_slug>/<run_id>/`。便捷回退输入包括 `04_recap_to_comfy_bridge/`、`05_assets_t2i/`、其下的资产子目录，或任一阶段中的文件；运行器会自动解析所需的两个阶段。"
    output_hint:
      en: "Writes one keyscene per beat plus `manifest.json` and payload dumps under `outputs/stories/<story>/<run>/06_keyscene_i2i/`."
      zh: "会在 `outputs/stories/<story>/<run>/06_keyscene_i2i/` 写出每个 beat 的关键帧、`manifest.json` 与 payload 调试文件。"
    starter_prompt:
      en: "Send the story run folder that already contains both `04_recap_to_comfy_bridge/` and `05_assets_t2i/`."
      zh: "请提供已经同时包含 `04_recap_to_comfy_bridge/` 与 `05_assets_t2i/` 的故事运行目录。"

steps:
  - number: 1
    title: Generate Keyscenes With ComfyUI Flux Kontext
    description: Resolve stage-04 storyboard beats and stage-05 assets, build per-beat ComfyUI API payloads, submit them to ComfyUI, and collect generated keyscene images.
    write_to: keyscene_manifest
    default: true

execution:
  strategy: utility_script
  utility_script:
    path: scripts/run_keyscene_kontext.py
    entrypoint: run

output:
  mode: text
  filename_template: manifest.json
  include_prompt_dump: false
---

# Recap To Keyscene Kontext

Use this skill for stage-06 recap keyscene I2I generation after stage 04 and stage 05 already exist for the same story run.

## Input

Preferred input:

- `outputs/stories/<story_slug>/<run_id>/`

Accepted single-path fallbacks:

- `outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/`
- `outputs/stories/<story_slug>/<run_id>/05_assets_t2i/`
- `outputs/stories/<story_slug>/<run_id>/05_assets_t2i/characters/`
- any file inside `04_recap_to_comfy_bridge/`
- any file inside `05_assets_t2i/` or its `characters/`, `scenes/`, `props/` subfolders

The runner resolves:

- storyboard: `04_recap_to_comfy_bridge/videoarc_storyboard.json`
- assets: `05_assets_t2i/characters`, `05_assets_t2i/scenes`, and `05_assets_t2i/props`

Legacy folders from earlier runs are still accepted:

- `03_recap_to_comfy_bridge`
- `04_assets_t2i`

Do not ask the user to choose individual asset image files.

## Workflow

The execution template is `assets/i2iscenes.json`. It is a ComfyUI API-format JSON template for a Flux Kontext FP8 image-to-image workflow. The runner preserves model and sampler nodes, then replaces per beat:

- `LoadImage` character, scene, and prop filenames
- reference stitch order across the two `ImageStitch` nodes
- positive prompt text
- `SaveImage.filename_prefix`
- `width` and `height` inputs where present
- `KSampler.seed`

Current bundled template chain:

- `190` character `LoadImage`
- `191` scene `LoadImage`
- `194` prop `LoadImage`
- `146` first `ImageStitch`
- `42` scale after stitch 1
- `192` second `ImageStitch`
- `195` final `FluxKontextImageScale`
- `124` `VAEEncode`
- `177` `ReferenceLatent`

The previous fixed behavior was effectively `character -> prop -> scene`:

- stitch 1 = `character + prop`
- stitch 2 = `(character + prop) + scene`

Set `ONE4ALL_KONTEXT_WORKFLOW_TEMPLATE` to point at a different exported ComfyUI API workflow JSON when replacing the bundled v1 template.

Default output is portrait-first for mobile recap viewing. v1 uses a lighter portrait baseline of `576x1024` to avoid unnecessary generation cost. For a higher-quality portrait run, override the size to `768x1344`; landscape remains possible through explicit width/height overrides but is not the default.

## Prompt Cleanup

Optional Gemini prompt cleanup runs before the final image prompt is injected into the workflow.

Purpose:

- normalize messy beat fields into a compact structured shot payload
- produce a shorter, cleaner final keyscene prompt
- optionally supply `shot_priority` (`identity|staging|object`) to the existing reference-order policy

Structured cleanup schema:

- `shot_intent`
- `framing`
- `performance`
- `scene`
- `essential_prop`
- `style_tail`
- `shot_priority`
- `negative_guidance`

Behavior:

- default: `gemini`
- optional override: `off`
- if Gemini succeeds, the runner assembles the final prompt from the validated structured fields
- if Gemini fails, times out, returns invalid JSON, or returns malformed fields, the runner logs a warning and falls back to the legacy prompt builder automatically

Config and overrides:

- config model alias: `model_aliases.gemini` in `config.ini`
- env: `ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODE=off|gemini`
- env: `ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODEL=gemini`
- CLI: `--prompt-cleanup-mode off|gemini`
- CLI: `--prompt-cleanup-model gemini`

Debugging:

- env: `ONE4ALL_KONTEXT_DEBUG_PROMPT_CLEANUP=1`
- CLI: `--debug-prompt-cleanup`

When debug is enabled, the runner writes per-beat artifacts with:

- structured input sent to Gemini
- raw Gemini response
- validated cleanup payload
- final assembled prompt
- legacy fallback prompt

## Reference Ordering

Supported modes:

- `identity_first`: `character -> scene -> prop`
- `staging_first`: `scene -> character -> prop`
- `object_first`: `prop -> scene -> character`

Auto mode is the default. The runner chooses shot-aware ordering with these rules:

- close-up / medium close-up / emotion / dialogue beats -> `identity_first`
- wide / establishing / staging-heavy / interaction beats -> `staging_first`
- insert / object-centric / prop-reveal beats -> `object_first`

Fallback behavior:

- 1 usable reference -> inject it directly into the final scale node
- 2 usable references -> stitch only the first two according to the chosen priority
- 3 usable references -> stitch the chosen first pair, then add the third reference in stitch 2

Manual overrides:

- global: `ONE4ALL_KONTEXT_REFERENCE_ORDER_MODE=identity_first|staging_first|object_first`
- CLI: `--reference-order-mode ...`
- per beat: `reference_order_mode` or `asset_hints.reference_order_mode`

Optional debug output:

- `ONE4ALL_KONTEXT_DEBUG_REFERENCE_ORDER=1`
- CLI: `--debug-reference-order`

Each beat manifest records the selected shot priority, final mode, chosen references in order, and target stitch / scale node mapping.

## Backend

ComfyUI must already be running for live runs. The endpoint resolves automatically from:

- `ONE4ALL_COMFYUI_URL`
- default `http://127.0.0.1:8188`

Live execution is the default behavior.

For live runs, local asset images are uploaded to ComfyUI through `/upload/image`, then the returned filenames are injected into `LoadImage` nodes. Set `ONE4ALL_COMFY_UPLOAD_IMAGES=0` to inject local paths directly instead.

Dry run is an advanced / optional path:

- CLI: `--dry-run`
- `ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODE=off|gemini`
- `ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODEL=gemini`
- `ONE4ALL_KONTEXT_DEBUG_PROMPT_CLEANUP=1`
- `ONE4ALL_KONTEXT_DRY_RUN=1`
- `ONE4ALL_KONTEXT_REFERENCE_ORDER_MODE=identity_first|staging_first|object_first`
- `ONE4ALL_KONTEXT_DEBUG_REFERENCE_ORDER=1`
- `ONE4ALL_KONTEXT_LIMIT=1`
- `ONE4ALL_KONTEXT_WIDTH=576`
- `ONE4ALL_KONTEXT_HEIGHT=1024`
- `ONE4ALL_KONTEXT_SEED=<integer>`

Higher portrait override:

- `ONE4ALL_KONTEXT_WIDTH=768`
- `ONE4ALL_KONTEXT_HEIGHT=1344`

## Validation

Before any ComfyUI submission, the runner validates:

- `04_recap_to_comfy_bridge/videoarc_storyboard.json`
- `05_assets_t2i/characters/`
- `05_assets_t2i/scenes/`
- `05_assets_t2i/props/`
- the chosen scene, character, and prop reference file for each beat

If a required path or selected reference image is missing, the skill fails clearly instead of sending a broken payload to ComfyUI. Beat-level preflight failures are recorded in `manifest.json` with additive `error_stage` and `missing_paths` fields.

## Output

The stage writes:

- `06_keyscene_i2i/<beat_id>.png` for live successful beats
- `06_keyscene_i2i/manifest.json`
- `06_keyscene_i2i/payloads/<beat_id>.json`

The manifest records the selected scene, character, and prop asset; matching strategy; prompt; seed; size; payload path; output path; status; ComfyUI prompt id when available; and fallback or limitation notes.
