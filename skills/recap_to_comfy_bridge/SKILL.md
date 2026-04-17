---
name: recap_to_comfy_bridge
display_name: Recap To Comfy Bridge
description: "Convert a `02_recap_production` recap bundle into bridge payloads: canonical `assets.json`, optional Qwen-compiled Z-Image prompts, legacy VideoArc-style assets, and storyboard JSON."
supports_resume: false
input_extensions:
  - .json
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "Recap To Comfy Bridge"
      zh: "解说产物转 Comfy 桥接"
    description:
      en: "Read a `02_recap_production` recap bundle and write canonical assets, optional Qwen-compiled Z-Image prompts, plus VideoArc-style bridge JSON payloads."
      zh: "读取 `02_recap_production` 解说产物包，并输出规范 assets 以及 VideoArc 风格桥接 JSON。"
    workflow_hint:
      en: "Stage 04 bridge. Preferred input is the Skill 2 `02_recap_production` folder; the bridge loads `04_episode_scene_script.json` plus sibling recap assets/image-config files, preferring JSON sidecars over txt fallbacks. Legacy `01_recap_production` folders are still accepted."
      zh: "第 04 阶段桥接。首选输入为第 2 个技能产出的 `02_recap_production` 文件夹；桥接会读取其中的 `04_episode_scene_script.json` 以及同级 recap 资产/生图配置文件，优先使用 JSON sidecar，必要时回退到 txt。旧版 `01_recap_production` 文件夹仍兼容。"
    input_hint:
      en: "Skill 4 input: send the Skill 2 `02_recap_production/` folder. Fallback: `02_recap_production/04_episode_scene_script.json`."
      zh: "第 4 个技能输入：请提供第 2 个技能产出的 `02_recap_production/` 文件夹。回退输入：`02_recap_production/04_episode_scene_script.json`。"
    output_hint:
      en: "Writes stage-04 outputs into `04_recap_to_comfy_bridge`: canonical `assets.json` with optional `compiled_prompt` fields, legacy `videoarc_assets.json`, `videoarc_storyboard.json`, and `bridge_summary.json`."
      zh: "会在 `04_recap_to_comfy_bridge` 阶段目录中写出：规范 `assets.json`、兼容旧链路的 `videoarc_assets.json`、`videoarc_storyboard.json` 和 `bridge_summary.json`。"
    starter_prompt:
      en: "Send the `02_recap_production` folder from Skill 2, or its `04_episode_scene_script.json` file."
      zh: "请提供第 2 个技能产出的 `02_recap_production` 文件夹，或其中的 `04_episode_scene_script.json` 文件。"

steps:
  - number: 1
    title: Build VideoArc Bridge Payloads
    description: Parse recap_production outputs and write VideoArc-style asset and storyboard JSON files.
    write_to: bridge_summary
    default: true

execution:
  strategy: utility_script
  utility_script:
    path: scripts/convert_recap_to_videoarc.py
    entrypoint: run

output:
  mode: text
  filename_template: bridge_summary.json
  include_prompt_dump: false
---

# Recap To Comfy Bridge

Convert the Skill 2 `02_recap_production` bundle into deterministic stage-04 bridge payloads that can feed older ComfyUI asset and storyboard logic.

## Expected Source Bundle

The bridge expects the recap stage folder:

- `outputs/stories/<story_slug>/<run_id>/02_recap_production/`

Inside that folder, it resolves these files:

- `02_assets.txt`
- `03_image_config.txt`
- `04_episode_scene_script.json`

Preferred user input:

- the `02_recap_production` folder itself

Fallback user input:

- the file `02_recap_production/04_episode_scene_script.json`

The shared runtime resolves folder input to `04_episode_scene_script.json`, then the bridge script derives the source folder from that file and validates the sibling recap artifacts before writing any outputs.

When the newer recap-production JSON sidecars exist, the bridge prefers:

- `02_assets.json`
- `03_image_config.json`

It falls back to:

- `02_assets.txt`
- `03_image_config.txt`

Public input contract notes:

- story run root input is supported only when the shared runtime can resolve it to `02_recap_production`
- do not pass `02_assets.json`, `03_image_config.json`, or bridge-stage `assets.json` as entry files

Legacy `01_recap_production` folders from earlier runs are still accepted.

## Output

Within the story-first run folder, stage 04 writes:

- `assets.json`
- `videoarc_assets.json`
- `videoarc_storyboard.json`
- `bridge_summary.json`

`assets.json` preserves the normalized deterministic fields and may add Qwen prompt-compiler fields per asset:

- `compiled_prompt`
- `compiled_prompt_model`
- `compiled_prompt_version`
- `compiled_prompt_source`
- `compiled_from_fields`
- `compiled_prompt_rationale`

The compiler uses the configured `qwen` model alias, currently `qwen/3-32b`, as a prompt compiler only. It is instructed to preserve source facts, enforce 2D/3D style, avoid multi-angle sheets/contact sheets/collages/split panels/labeled angles, and produce one clean Z-Image asset prompt for each character, scene, or prop.

If Qwen is unavailable or a compile call fails, the bridge does not fail the stage. It keeps the deterministic normalized fields and records fallback status in `bridge_summary.json` under `qwen_prompt_compiler`.

Set `ONE4ALL_QWEN_ASSET_PROMPT_COMPILER=0` to force the deterministic fallback path for bridge validation or offline runs.

## Bridge Scope

This skill is an adapter and prompt-compilation layer. It does not:

- run ComfyUI
- rebuild the old VideoArc webapp
- generate images or clips itself
- replace the recap_production workflow

It only reshapes current recap outputs into stable, inspectable JSON payloads for downstream legacy rendering logic.
