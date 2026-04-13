---
name: recap_to_comfy_bridge
display_name: Recap To Comfy Bridge
description: Convert a recap_production output folder or its `04_episode_scene_script.json` into deterministic VideoArc-style bridge payloads for legacy ComfyUI asset and storyboard workflows.
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
      en: "Read recap_production outputs and write VideoArc-style bridge JSON payloads for the older ComfyUI pipeline."
      zh: "读取 recap_production 的产物，并输出可供旧 ComfyUI 流程复用的 VideoArc 风格桥接 JSON。"
    workflow_hint:
      en: "This bridge is deterministic and script-backed. Point it at a recap_production run folder or the folder's `04_episode_scene_script.json`, and it will derive sibling recap artifacts automatically."
      zh: "该桥接流程为本地脚本确定性执行。把它指向一个 recap_production 运行目录或其中的 `04_episode_scene_script.json`，脚本会自动读取同级 recap 产物。"
    input_hint:
      en: "Send a recap_production output folder that contains `04_episode_scene_script.json`, or send that JSON file directly."
      zh: "请提供包含 `04_episode_scene_script.json` 的 recap_production 输出目录，或直接提供该 JSON 文件。"
    output_hint:
      en: "Writes `videoarc_assets.json`, `videoarc_storyboard.json`, and `bridge_summary.json` into the current project output folder."
      zh: "会在当前项目输出目录中写出 `videoarc_assets.json`、`videoarc_storyboard.json` 和 `bridge_summary.json`。"
    starter_prompt:
      en: "Send the recap_production run folder you want to bridge into VideoArc-style payloads."
      zh: "请提供要桥接成 VideoArc 风格载荷的 recap_production 运行目录。"

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

Convert current `recap_production` outputs into deterministic VideoArc-style JSON payloads that can feed older ComfyUI asset and storyboard logic.

## Expected Source Bundle

The bridge expects a `recap_production` run folder with these top-level files:

- `02_assets.txt`
- `03_image_config.txt`
- `04_episode_scene_script.json`

The user may send either:

- the run folder itself
- or the file `04_episode_scene_script.json`

The bridge script derives the source folder from that JSON file and validates the sibling files before writing any outputs.

## Output

Within the normal ONE4ALL output root, the bridge writes:

- `videoarc_assets.json`
- `videoarc_storyboard.json`
- `bridge_summary.json`

## Bridge Scope

This skill is a fast adapter layer only. It does not:

- run ComfyUI
- rebuild the old VideoArc webapp
- generate images or clips itself
- replace the recap_production workflow

It only reshapes current recap outputs into stable, inspectable JSON payloads for downstream legacy rendering logic.
