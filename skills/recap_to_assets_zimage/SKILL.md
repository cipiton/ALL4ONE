---
name: recap_to_assets_zimage
display_name: Recap To Assets Z-Image
description: Generate character, scene, and prop T2I assets from an `assets.json` package by calling the local Z-Image-Turbo Python backend.
supports_resume: false
input_extensions:
  - .json
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "Recap To Assets Z-Image"
      zh: "解说资产生图 Z-Image"
    description:
      en: "Read `assets.json`, group assets into characters/scenes/props, and generate local Z-Image-Turbo images into the story-first stage folder."
      zh: "读取 `assets.json`，按角色/场景/道具分组，并在故事优先输出结构里用本地 Z-Image-Turbo 生成图片。"
    workflow_hint:
      en: "Stage 05 T2I assets. Preferred input is the Skill 4 `04_recap_to_comfy_bridge` folder or its canonical `assets.json`; the runner then calls the local Z-Image backend."
      zh: "第 05 阶段 T2I 资产。首选输入为第 4 个技能产出的 `04_recap_to_comfy_bridge` 文件夹，或其中的规范 `assets.json`；随后运行器会调用本地 Z-Image 后端。"
    input_hint:
      en: "Skill 5 input: send `04_recap_to_comfy_bridge/assets.json` from Skill 4. You may also send the `04_recap_to_comfy_bridge/` folder or the story run folder."
      zh: "第 5 个技能输入：请提供第 4 个技能产出的 `04_recap_to_comfy_bridge/assets.json`。也可以提供 `04_recap_to_comfy_bridge/` 文件夹或故事运行目录。"
    output_hint:
      en: "Writes generated images plus `manifest.json` under `outputs/stories/<story>/<run>/05_assets_t2i/characters|scenes|props/`."
      zh: "会把生成图片和 `manifest.json` 写入 `outputs/stories/<story>/<run>/05_assets_t2i/characters|scenes|props/`。"
    starter_prompt:
      en: "Send the Skill 4 `04_recap_to_comfy_bridge/assets.json` file, or the bridge/story run folder that contains it."
      zh: "请提供第 4 个技能产出的 `04_recap_to_comfy_bridge/assets.json` 文件，或包含该文件的桥接/故事运行文件夹。"

steps:
  - number: 1
    title: Generate T2I Assets With Z-Image-Turbo
    description: Parse assets.json and render one image per asset through the local Z-Image-Turbo backend.
    write_to: asset_manifest
    default: true

execution:
  strategy: utility_script
  utility_script:
    path: scripts/generate_assets_zimage.py
    entrypoint: run

output:
  mode: text
  filename_template: manifest.json
  include_prompt_dump: false
---

# Recap To Assets Z-Image

Render recap asset prompts into local T2I images with the workspace's `z-image` checkout and venv.

## Expected Input

Preferred input:

- `outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/assets.json`

Accepted folder inputs:

- `outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/`
- `outputs/stories/<story_slug>/<run_id>/`

The selected `assets.json` file should contain grouped arrays under:

- `characters`
- `scenes`
- `props`

Each asset entry should expose practical generation fields:

- `asset_id` or `name`
- optional `compiled_prompt` from Skill 4 Qwen prompt compilation
- structured fields such as `style_preset`, `style_hint`, `style_lighting`, `core_feature`, `subject_content`, `description`, `prompt_fields`, and `source.raw_lines`
- `prompt` or `prompt_text` as a fallback only

The stage consumes the canonical bridge `assets.json`; do not pass individual image files.

## Output

Within the story-first run folder, this skill writes:

- `05_assets_t2i/characters/*.png`
- `05_assets_t2i/scenes/*.png`
- `05_assets_t2i/props/*.png`
- `05_assets_t2i/manifest.json`

Default sizes:

- character: 512x768 portrait full-body reference
- scene: 768x512 landscape
- prop: 512x512 square

Prompts prefer Skill 4 `compiled_prompt` when present. Without it, they are assembled structured-first at render time from `style_preset` / `style_hint` / `style_lighting`, `core_feature`, `subject_content`, `description`, character role/traits, `prompt_fields`, and `source.raw_lines`; flattened `prompt` / `visual_prompt` strings are fallback material only.

Style is enforced before the asset description. In 2D mode, each prompt receives an asset-type-specific anime / 动漫风格 illustration mandate:

- characters: high-quality anime style 2D character illustration, 动漫风格, mature animated-drama character design, refined anime linework, detailed painted shading
- scenes: high-quality anime style 2D background illustration, 动漫风格, cinematic anime environment art, layered painted atmosphere, dramatic light and shadow
- props: high-quality anime style 2D prop illustration, 动漫风格, anime production asset design, refined anime linework, detailed painted materials, not product render, not studio product photo

In 3D mode, each prompt receives a parallel stylized 3D CG mandate for character, environment, or prop assets. Flattened prompt text cannot override the structured style decision.

When `compiled_prompt` exists, the runner uses it as the primary Z-Image prompt, still strips legacy layout wording, and adds missing local style/output guardrails only when needed. Old bridge outputs without `compiled_prompt` keep working through the structured fallback builders.

Character prompts are normalized into a single-person identity reference style:

- one front-facing full-body character
- neutral standing pose
- clean/simple background
- no sheet or board-style layout

Scene prompts are rebuilt as single clean environment references. Props are rebuilt as one clean prop image by default, without multi-view reference-sheet instructions. Specialized props are detected at render time and enriched with category-specific morphology:

- motorcycles, trail bikes, dirt bikes, off-road bikes, and sport motorcycle prototypes
- motorcycle, motocross, and enduro helmets
- motorcycle engines, especially inline-three / triple-cylinder engines

The prop prompt builder preserves available bridge fields such as `subject_content`, `style_lighting`, `description`, and useful cleaned `source.raw_lines`, then adds concise category geometry and negative constraints such as not bicycle, not cycling helmet, or not V-twin when applicable. Uncommon mechanical assets can still need more explicit source wording if they do not contain recognizable category terms.

## Runtime Notes

- the skill calls the local Z-Image backend Python directly and does not depend on shell activation
- it forces `ZIMAGE_ATTENTION=native` for generation
- character, scene, and prop prompt normalization use existing bridge fields and do not change the input contract or bridge-stage output
- legacy sheet / board / multi-view wording is defensively filtered during prompt assembly; new recap prompt sources no longer request those layouts by default
- 2D mode includes anti-realism wording, especially for props and scenes, to discourage photorealistic, realistic 3D, product-render, and studio-photo drift
- default backend paths are resolved from:
  - `z-image/.venv/Scripts/python.exe`
  - `z-image/ckpts/Z-Image-Turbo`
- supported environment overrides:
  - `ONE4ALL_ZIMAGE_REPO`
  - `ONE4ALL_ZIMAGE_PYTHON`
  - `ONE4ALL_ZIMAGE_MODEL`
- v1 records per-asset failures in the stage `manifest.json` and continues with the remaining assets instead of aborting the whole stage on the first failure
