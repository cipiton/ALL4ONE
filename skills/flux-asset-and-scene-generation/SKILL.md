---
name: flux-asset-and-scene-generation
display_name: FLUX Asset and Scene Generation
description: Agentic FLUX.2 klein production workflow for turning recap-production or cp-production outputs into reusable assets, keyscenes, or both. Use when ChatGPT should decide whether to generate assets, scenes, or a chained asset-to-scene pass, normalize the available planning files, preserve continuity, and then hand deterministic execution to the local FLUX runner.
supports_resume: true
input_extensions:
  - .json
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "FLUX Asset and Scene Generation"
      zh: "FLUX 资产与关键场景生成"
    description:
      en: "Read recap-production or cp-production planning bundles, decide the safest FLUX image workflow, and run local asset and keyscene generation."
      zh: "读取 recap-production 或 cp-production 规划包，决定最合适的 FLUX 生图流程，并执行本地资产与关键场景生成。"
    workflow_hint:
      en: "The skill normalizes the source bundle, decides assets vs keyscenes vs both, reuses existing assets when possible, then executes the deterministic FLUX run."
      zh: "技能会先规范化输入包，再决定跑资产、关键场景或两者串联，优先复用已有资产，然后执行确定性的 FLUX 流程。"
    input_hint:
      en: "Send `02_recap_production/`, legacy `01_recap_production/`, the story run folder that contains them, `04_episode_scene_script.json`, or a `cp-production` output folder such as `outputs/cp-production/<job>/`."
      zh: "可提供 `02_recap_production/`、旧版 `01_recap_production/`、包含它们的故事运行目录、`04_episode_scene_script.json`，或 `outputs/cp-production/<job>/` 这类 `cp-production` 输出目录。"
    output_hint:
      en: "Writes `generated_assets/`, `generated_keyscenes/`, and manifest/debug files that record the normalized source contract, planning decisions, and generated outputs."
      zh: "会写入 `generated_assets/`、`generated_keyscenes/` 以及记录输入契约、规划决策和生成结果的 manifest/debug 文件。"
    starter_prompt:
      en: "Choose the skill, give the recap or cp-production folder, then answer with `1`, `2`, `3`, or a short goal such as `reuse existing assets and continue to keyscenes`."
      zh: "选择技能后提供 recap 或 cp-production 目录，再回复 `1`、`2`、`3`，或直接描述目标，例如“复用已有资产继续生成关键场景”。"
  startup:
    mode: explicit_step_selection
    default_step: 1
    allow_resume: true
    allow_auto_route: false
  execution:
    mode: single_step
    continue_until_end: false
    preview_before_save: false
    save_only_on_accept: false

references:
  - id: prompt_writing
    path: references/prompt-writing.md
    kind: reference
    load: always
  - id: asset_prompting
    path: references/asset-prompting.md
    kind: reference
    load: always
  - id: scene_prompting
    path: references/scene-prompting.md
    kind: reference
    load: always
  - id: prompt_policy
    path: references/prompt-policy.md
    kind: reference
    load: always
  - id: continuity_rules
    path: references/continuity-rules.md
    kind: reference
    load: always
  - id: input_routing
    path: references/input-routing.md
    kind: reference
    load: always
  - id: output_contract
    path: references/output-contract.md
    kind: reference
    load: always
  - id: examples
    path: references/examples.md
    kind: reference
    load: always
  - id: flux_prompting
    path: references/flux2-klein-prompting-application.md
    kind: reference
    load: always

steps:
  - number: 1
    title: Generate FLUX Assets or Keyscenes
    description: Normalize the planning bundle, choose the safest asset/keyscene workflow, and execute the local FLUX run.
    write_to: manifest
    output_filename: manifest.json
    default: true

execution:
  strategy: utility_script
  utility_script:
    path: scripts/run_flux_generation.py
    entrypoint: run

output:
  mode: text
  filename_template: manifest.json
  include_prompt_dump: false
---

# Skill Instructions

Use this skill when the source material is already in a structured preproduction bundle and the next job is FLUX still-image generation.

The skill owns the workflow decisions and the prompt-writing policy. The LLM authors the final FLUX.2 klein prompt from the skill references. Scripts only normalize inputs, choose and label references, invoke the local FLUX runner, and save manifests. A deterministic Python prompt builder remains only as a fallback if LLM prompt authoring fails.

## Source Contracts

Treat these as first-class inputs:

- `02_recap_production/`
- legacy `01_recap_production/`
- a story run folder that contains one of those stage folders
- `04_episode_scene_script.json`
- a `cp-production` output folder such as `outputs/cp-production/<job>/`

For `cp-production`, the useful files are:

- `02_beat_sheet.json`
- `03_asset_registry.json`
- `04_anchor_prompts.json`
- optional `05_video_prompts.json`
- optional `01_narration_script.txt`

Do not require `cp-production` to fake recap-production filenames.

## Workflow Ownership

Before executing generation:

1. Normalize the input bundle into one internal planning shape.
2. Decide whether the run should be:
   - assets only
   - keyscenes only
   - assets then keyscenes
3. Reuse existing generated assets when that preserves continuity and avoids unnecessary regeneration.
4. Stop clearly when the source contract is too incomplete to produce a reliable result.

## Decision Rules

- Treat `characters`, `props`, and `scenes` as the asset groups.
- Treat beat-level integrated stills built from those assets as keyscenes.
- Asset generation is necessary before keyscenes when no usable generated assets exist and a structured asset source is available.
- Existing generated assets can be reused when they already satisfy continuity needs for the requested run.
- If the user asks for keyscenes only but no usable generated assets exist, prefer switching to assets then keyscenes when an asset source is available.
- If the user asks for assets only and no structured asset source exists, stop clearly instead of inventing placeholders.
- If beat planning is missing but anchor prompts exist, derive keyscene planning from anchor prompts rather than failing immediately.
- If only partial source files are available, proceed only when the remaining files are sufficient for a controlled result.

## Prompt Policy

- Raw narrative prose is source material, not a direct FLUX prompt.
- Asset prompts describe one reusable reference image at a time.
- Keyscene prompts describe one integrated still-image story instant at a time.
- The LLM authors the final FLUX klein prompt using the reference files, because FLUX klein performs better with scene-first prose prompting and explicit lighting control.
- Final prompts must remain single-language according to `[generation] final_prompt_language` in `config.ini`.
- Reference images should carry identity and design detail; prompts should focus on the target composition and relation.
- Default FLUX output resolution comes from `[flux_generation]` in `config.ini`; explicit runtime or CLI `width`/`height` values override config values.

Read the references for the operational rules:

- `references/prompt-writing.md`
- `references/asset-prompting.md`
- `references/scene-prompting.md`
- `references/input-routing.md`
- `references/continuity-rules.md`
- `references/prompt-policy.md`
- `references/output-contract.md`
- `references/examples.md`
- `references/flux2-klein-prompting-application.md`

## Output Contract

The skill should emit:

- `generated_assets/` when assets are generated
- `generated_keyscenes/` when keyscenes are generated
- `manifest.json` for each run
- one `*.resolved_prompt.txt` file beside each generated image
- debug JSON for keyscene selection when debug mode is enabled

Each manifest should record:

- normalized input contract
- source files used
- workflow-plan decision
- selected style target
- final prompt language
- whether the prompt was LLM-authored or fallback-authored
- selected references and fallback notes
- output file paths

## Continuity Policy

- Reuse scene and character references by default for keyscenes.
- Add prop references only when they are story-critical or the shot is insert-like.
- Keep naming stable so previously generated assets can be matched deterministically.
- Prefer stopping over silently breaking continuity when image-conditioning inputs are absent.
