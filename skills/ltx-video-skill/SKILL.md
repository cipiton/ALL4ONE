---
name: ltx-video-skill
display_name: LTX Video Skill
description: Read a recap production or cp-production output folder, extract shot beats, call the configured `gemini` model alias from `config.ini` as a prompt director, and save structured LTX-ready video prompts for later clip generation. Use when Codex should create shot-level motion prompts from recap-production or cp-production outputs without rendering video yet.
supports_resume: false
input_extensions:
  - .json
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "LTX Video Skill"
      zh: "LTX 视频提示词技能"
    description:
      en: "Turn recap-production or cp-production beats into structured LTX-ready shot prompts with the configured Gemini alias."
      zh: "将 recap-production 或 cp-production 的分镜 beat 转换为结构化 LTX 视频提示词，并使用已配置的 Gemini 别名。"
    workflow_hint:
      en: "This v1 skill reads a recap-production or cp-production folder, directs Gemini to rewrite each beat into a structured motion prompt, validates the JSON, and saves prompt outputs for later clip generation."
      zh: "这个 v1 技能会读取 recap-production 或 cp-production 文件夹，调用 Gemini 将每个 beat 改写为结构化动态提示词，校验 JSON，并保存供后续视频生成使用的提示词结果。"
    input_hint:
      en: "Send the `02_recap_production/` folder, the legacy `01_recap_production/` folder, the story run folder that contains one of them, `04_episode_scene_script.json`, or a cp-production folder containing `02_beat_sheet.json` and `05_video_prompts.json`."
      zh: "请提供 `02_recap_production/`、兼容旧链路的 `01_recap_production/`、包含其一的故事运行目录、`04_episode_scene_script.json`，或包含 `02_beat_sheet.json` 和 `05_video_prompts.json` 的 cp-production 输出目录。"
    output_hint:
      en: "Writes `generated_ltx_prompts/prompts.json`, `prompts_by_episode.json`, optional `debug/`, and `manifest.json`."
      zh: "会写出 `generated_ltx_prompts/prompts.json`、`prompts_by_episode.json`、可选 `debug/` 和 `manifest.json`。"
    starter_prompt:
      en: "Use this skill when you have a recap production folder and want structured LTX-ready shot prompts, not rendered clips."
      zh: "当你已经有 recap production 文件夹，并且只需要结构化 LTX 分镜提示词而不是视频渲染时，使用这个技能。"

steps:
  - number: 1
    title: Generate LTX Prompt Pack
    description: Read the recap production bundle, direct Gemini to rewrite each shot beat into LTX-ready prompt JSON, validate the results, and save a prompt pack for later clip generation.
    write_to: manifest
    default: true

execution:
  strategy: utility_script
  utility_script:
    path: scripts/run_ltx_prompt_generation.py
    entrypoint: run

output:
  mode: text
  filename_template: manifest.json
  include_prompt_dump: false
---

# LTX Video Skill

Use this skill when recap production or cp-production has already produced planning outputs and the next need is shot-level video prompting, not clip rendering. The current prompt builder is aligned to the official LTX 2.3 prompting guidance from:

- `https://ltx.io/model/model-blog/ltx-2-3-prompt-guide`
- `https://docs.ltx.video/api-documentation/prompting-guide`

It converts recap-style beat text into structured LTX-ready motion prompts that are more shot-directed, less recap-like, and safer for later image-to-video generation.

## Workflow

1. Ask for the recap-production or cp-production output folder path.
2. Read the input bundle through one normalization layer:
   - recap-production prefers `04_episode_scene_script.json`
   - cp-production reads `02_beat_sheet.json` and `05_video_prompts.json`, plus optional `03_asset_registry.json` and `04_anchor_prompts.json`
3. Normalize both contracts into the same internal shot bundle shape.
4. Call the configured `gemini` alias from `config.ini` as a prompt director for one beat at a time.
5. Normalize Gemini into an internal shot schema.
6. Assemble the final prompt as a single LTX-style paragraph from the structured fields.
7. Validate the result against motion, camera, sentence-count, and anti-recap rules.
8. If Gemini fails or returns weak output, fall back to a deterministic local prompt builder that still follows the LTX rules better than the old v1 one-line template.
9. When downstream keyscene images already exist, record them as the preferred image-conditioning source for later clip stages.
10. Save structured outputs under `generated_ltx_prompts/`.

## Expected Input

Preferred inputs:

- `outputs/stories/<story_slug>/<run_id>/02_recap_production/`
- legacy fallback: `outputs/stories/<story_slug>/<run_id>/01_recap_production/`
- the story run folder that contains one of those stage folders
- `04_episode_scene_script.json`
- `outputs/cp-production/<job>/`

Required recap-production file:

- `04_episode_scene_script.json`

Required cp-production files:

- `02_beat_sheet.json`
- `05_video_prompts.json`

Optional cp-production supporting files:

- `03_asset_registry.json`
- `04_anchor_prompts.json`
- `01_narration_script.txt`

Optional recap-production supporting files:

- `04_episode_scene_script.md`
- `02_assets.json`
- `03_image_config.json`

If multiple relevant files exist, the skill prefers the canonical JSON scene script and records what it selected in the manifest.

For cp-production inputs, the loader uses:

- `02_beat_sheet.json` as the beat / shot planning source
- `05_video_prompts.json` as the primary motion prompt source
- `04_anchor_prompts.json` as optional still-image setup context
- `03_asset_registry.json` as optional linked-asset context

The skill does not confuse prompt files with actual images. If real generated keyscene images are found in nearby downstream folders such as `generated_keyscenes/` or `06_keyscene_i2i/`, those image paths are recorded per shot as the preferred image-conditioning source for a later render stage.

## What Gemini Does

Gemini is used as a prompt director, not as a video model. For each beat, it rewrites recap-style prose into a structured intermediate payload with fields such as:

- `episode_id`
- `shot_id`
- `shot_type`
- `shot_mode`
- `scene_setup`
- `character_definition`
- `action_sequence`
- `camera_motion`
- `environment_motion`
- `audio_description`
- `acting_cues`
- `duration_hint`
- `final_prompt`

The final prompt is then rendered as one coherent paragraph focused on what a viewer should literally see happening next.

Internal shot modes currently include:

- `closeup_emotion`
- `dialogue_speaking`
- `insert_prop_detail`
- `staging_environment`
- `action_movement`

These modes change how much detail is kept, how camera language is phrased, whether audio is useful, and how strongly acting cues are surfaced.

## Prompting Rules

The skill directs Gemini to follow the LTX 2.3 guidance more closely:

- one shot equals one prompt
- write a single flowing paragraph
- default to roughly 4-8 descriptive sentences, adjusted by shot mode and duration
- keep action in present-tense Chinese phrasing
- write a real sequence: opening state, primary movement, secondary reaction, camera behavior
- convert abstract emotions into visible cues such as breath, pauses, glances, jaw tension, grip changes, and head turns
- include scene, action, character, camera, and optional audio only when they help motion readability
- match detail to shot scale
- keep motion concrete and physically plausible
- avoid recap narration, theme explanation, symbolic summary, and story-meaning filler
- avoid overloading the shot with conflicting lighting, complex physics, too many actions, or readable text/logos
- keep one beat to one shot prompt

For image-to-video use cases, the builder explicitly biases toward what moves next, how the camera moves next, what secondary motion appears next, and what sound emerges next. It avoids re-describing static setup too heavily if the source image or keyframe would already establish it.

## Validation And Fallback

The validator checks for:

- single-paragraph output
- shot-aware sentence-count ranges
- visible action progression
- camera motion or an explicit static-frame choice
- no recap-summary language
- not being too short for longer clips
- no mixed-language leakage in the final Chinese prompt
- slideshow-like patterns such as static one-liners or emotion-only descriptions

If Gemini output fails validation, the skill records the reason, switches to the deterministic fallback builder, and keeps writing the same structured schema plus the final rendered prompt.

## Output Layout

- `generated_ltx_prompts/prompts.json`
- `generated_ltx_prompts/prompts_by_episode.json`
- `generated_ltx_prompts/manifest.json`
- `generated_ltx_prompts/debug/*.json` when debug output is enabled

Manifest fields include:

- input folder
- timestamp
- selected episode-scene script path
- model alias used
- resolved model route
- shot count
- success / fallback counts
- validation summary
- output paths

Per-shot items and debug files now also keep:

- source contract
- source beat text and source visual/context fields
- source video prompt and source anchor prompt when available
- the structured intermediate fields used to assemble the prompt
- the raw Gemini response text / JSON
- validation result and issues
- final prompt
- discovered image-conditioning path when a real keyscene image was found
- fallback reason when fallback was used

## Local Execution

Interactive:

```powershell
python skills\ltx-video-skill\scripts\run_ltx_prompt_generation.py
```

Non-interactive example:

```powershell
python skills\ltx-video-skill\scripts\run_ltx_prompt_generation.py `
  --recap-folder outputs\cp-production\zxmoto__20260417_102521 `
  --model-alias gemini `
  --debug-output `
  --limit 3 `
  --non-interactive
```

Useful flags:

- `--model-alias gemini`
- `--limit <int>`
- `--shot-id <epXX_sYY>`
- `--output-root <dir>`
- `--debug-output`
- `--non-interactive`

## Script Map

- `scripts/run_ltx_prompt_generation.py`: utility runner, progress output, prompt generation loop, output writing
- `scripts/load_recap_production.py`: recap/cp-production resolution, normalization, beat extraction, and keyscene-image discovery
- `scripts/build_ltx_prompt_requests.py`: LTX-oriented request building, shot-mode selection, structured fallback fields, and final prompt assembly
- `scripts/gemini_prompt_director.py`: Gemini call, JSON parsing, schema normalization, validation, and fallback routing
- `scripts/validate_ltx_prompts.py`: prompt-output validation, slideshow-pattern detection, and malformed-response self-test tooling

## Prompting Notes

Read `references/ltx-prompting-notes.md` when adjusting prompt shape or validation rules.

## Scope Guard

v1 does not render video clips. It only writes structured prompt packs. A future v2 can later:

- read these prompt outputs
- pair them with keyframes or keyscenes
- call an LTX backend to render clips

## Caveats

- Real Gemini calls depend on the configured OpenRouter/OpenAI environment keys and the `gemini` alias in `config.ini`.
- Prompt quality is still bounded by recap beat quality. Weak or overly abstract beats will trigger more fallback prompts.
- The skill now follows official LTX 2.3 prompt-shape guidance, but it still stops at prompt-pack generation. It does not yet render video, manage timing, stitch clips, or retry failed generations.
