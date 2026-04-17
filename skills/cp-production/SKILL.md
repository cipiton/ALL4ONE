---
name: cp-production
display_name: CP Production
description: Multi-step production workflow for turning a raw story `.txt` into a narration-ready script, structured beat sheet, reusable asset registry, FLUX.2 klein anchor-image prompts, and LTX-2 motion-first video prompts.
supports_resume: true
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "CP Production"
      zh: "CP 制作前期"
    description:
      en: "Turn a raw story text into a staged production package with narration, beats, assets, anchor-image prompts, and video prompts."
      zh: "将原始故事文本转为分阶段制作前期包，输出旁白脚本、视觉节拍、资产注册表、关键帧提示词和视频提示词。"
    workflow_hint:
      en: "This workflow runs step by step: narration script, beat sheet, asset registry, anchor prompts, then video prompts."
      zh: "此流程按步骤运行：先输出旁白脚本，再生成视觉节拍表、资产注册表、关键帧提示词，最后生成视频提示词。"
    input_hint:
      en: "Send a raw `.txt` story, novel chapter, or prose draft to build the cp-production package."
      zh: "请提供原始 `.txt` 故事、小说章节或 prose 草稿，用于生成 cp-production 制作前期包。"
    output_hint:
      en: "Writes accepted cp-production outputs into the run folder with readable txt/md files plus machine-readable JSON sidecars."
      zh: "会把已接受的 cp-production 步骤结果写入运行目录，保留可读的 txt/md 文件，并生成机器可读 JSON sidecar。"
    starter_prompt:
      en: "Send the source `.txt` story draft for CP Production."
      zh: "请提供用于 CP Production 的源 `.txt` 故事稿。"
  startup:
    mode: explicit_step_selection
    default_step: 1
    allow_resume: true
    allow_auto_route: false
  execution:
    mode: sequential_with_review
    continue_until_end: true
    preview_before_save: true
    save_only_on_accept: true

steps:
  - number: 1
    title: 输出旁白脚本
    prompt_reference: step1_prompt
    write_to: narration_script
    output_filename: 01_narration_script.txt
    default: true
    route_keywords_any:
      - 小说
      - 故事
      - 章节
      - prose
      - novel
      - story
      - chapter
      - narration
      - raw text
    route_priority: 1
    input_blocks:
      - label: 【原始故事文本】
        from: user_brief
  - number: 2
    title: 输出视觉节拍表
    prompt_reference: step2_prompt
    write_to: beat_sheet
    output_filename: 02_beat_sheet.md
    json_write_to: beat_sheet_json
    json_output_filename: 02_beat_sheet.json
    route_keywords_any:
      - beat
      - beat sheet
      - visual beat
      - scene beat
      - shot plan
      - 节拍
      - 分镜规划
    input_blocks:
      - label: 【旁白脚本】
        from: narration_script
  - number: 3
    title: 提炼资产注册表
    prompt_reference: step3_prompt
    write_to: asset_registry
    output_filename: 03_asset_registry.txt
    json_write_to: asset_registry_json
    json_output_filename: 03_asset_registry.json
    route_keywords_any:
      - asset
      - registry
      - character
      - prop
      - vehicle
      - environment
      - 资产
      - 角色
      - 道具
      - 场景
    input_blocks:
      - label: 【旁白脚本】
        from: narration_script
      - label: 【视觉节拍表】
        from: beat_sheet
  - number: 4
    title: 输出关键帧提示词
    prompt_reference: step4_prompt
    write_to: anchor_prompts
    output_filename: 04_anchor_prompts.txt
    json_write_to: anchor_prompts_json
    json_output_filename: 04_anchor_prompts.json
    route_keywords_any:
      - anchor
      - keyscene
      - flux
      - still image
      - anchor prompt
      - 关键帧
      - 锚帧
      - 生图提示词
    input_blocks:
      - label: 【视觉节拍表】
        from: beat_sheet
      - label: 【资产注册表】
        from: asset_registry
  - number: 5
    title: 输出视频提示词
    prompt_reference: step5_prompt
    write_to: video_prompts
    output_filename: 05_video_prompts.txt
    json_write_to: video_prompts_json
    json_output_filename: 05_video_prompts.json
    route_keywords_any:
      - video prompt
      - ltx
      - motion
      - camera movement
      - 视频提示词
      - 动作提示词
      - 镜头运动
    input_blocks:
      - label: 【视觉节拍表】
        from: beat_sheet
      - label: 【资产注册表】
        from: asset_registry
      - label: 【关键帧提示词】
        from: anchor_prompts

references:
  - id: step1_prompt
    path: references/step1-prompt.md
    kind: prompt
    step_numbers:
      - 1
  - id: step2_prompt
    path: references/step2-prompt.md
    kind: prompt
    step_numbers:
      - 2
  - id: step3_prompt
    path: references/step3-prompt.md
    kind: prompt
    step_numbers:
      - 3
  - id: step4_prompt
    path: references/step4-prompt.md
    kind: prompt
    step_numbers:
      - 4
  - id: step5_prompt
    path: references/step5-prompt.md
    kind: prompt
    step_numbers:
      - 5
  - id: workflow_reference
    path: references/workflow.md
    kind: reference
    load: always
  - id: output_schema
    path: references/output-schema.md
    kind: reference
    step_numbers:
      - 1
      - 2
      - 3
      - 4
      - 5
  - id: prompt_rules
    path: references/prompt-rules.md
    kind: reference
    step_numbers:
      - 2
      - 3
      - 4
      - 5
  - id: examples_reference
    path: references/examples.md
    kind: reference
    step_numbers:
      - 2
      - 3
      - 4
      - 5

execution:
  strategy: step_prompt

output:
  mode: text
  filename_template: "step_{step_number}_output.txt"
  include_prompt_dump: true
---

# Skill Instructions

协助完成 ONE4ALL 的第一阶段制作前期整理，并严格保持以下产物分离：

- `narration_script`
- `beat_sheet`
- `asset_registry`
- `anchor_prompts`
- `video_prompts`

这是生产前置流程，不是直接给图像模型或视频模型喂原始小说 prose 的流程。

## 全局执行规则

- 从用户选择的起始步骤开始执行；共享运行时会在每一步生成草稿后先预览，再由用户选择接受、改进、重来、查看全文或取消。
- 只有用户接受的结果才会保存为当前步骤输出；一旦接受，共享运行时会自动继续到下一步，直到流程结束或用户取消。
- 如果运行被中断，共享引擎可基于最近一次已接受的步骤进行 resume。
- 原始故事 prose 是源材料，不是提示词材料。
- 旁白脚本、视觉节拍、资产注册表、关键帧提示词、视频提示词必须视为五种不同工件，不允许混写。
- 视觉节拍必须包含内部 scene dramatization / 场景戏剧化设计，用于后续提示词推导；但不要把旁白、锚帧提示词和视频提示词重新合并成一个 recap 式产物。
- 保留故事顺序、角色关系、关键转折和主要戏剧弧线。
- 场景戏剧化不能改变资产事实：摩托车不能写成汽车，`ZXMOTO 820RR-RS` 必须是 racing motorcycle / sportbike / 摩托赛车，motorcycle frame 不能写成 car chassis，道具、服装、地点和车辆比例必须保持注册表与 beat 连续性。
- 优先保证制作可用性，不要为了文学化表达牺牲结构清晰度。
- 不是每一个 beat 都必须生成完整视频 clip；必要时应明确标记某个 beat 只适合旁白支撑、插入镜头或关键帧锚点。

## 产物设计原则

- 步骤一只负责把故事改写成适合配音/旁白的脚本，不生成提示词。
- 步骤二负责把故事拆成稳定的生产节拍，供后续资产与提示词共用；每个 beat 还要携带 `visual_core`、`dramatic_focus`、`continuity_notes`、`emotional_pressure`、`strongest_single_frame_interpretation`、`strongest_motion_interpretation`、`shot_design`、`camera_intent` 等 scene dramatization 字段。
- 步骤三负责提炼可复用资产，避免下游每个 beat 都重新发明角色与场景。
- 步骤四负责面向 FLUX.2 klein 的静帧/关键帧提示词，重点是从 scene dramatization 渲染强单帧镜头，不是动作过程或字段拼接。
- 步骤五负责面向 LTX-2 的运动提示词，默认锚帧已经定义主体、场景与风格，因此重点写锚帧之后的动作、环境变化与镜头运动。
- 当视觉风格为 `3D` 时，默认 3D 子类型为 `anime_donghua_3d`，即 anime/donghua inspired premium East Asian CG；除非用户明确要求，不要写成 Pixar-like、Disney-like、toy-like 或 rounded family animation。

## Step Rules

### 步骤一

- 读取原始 `.txt` 故事文本，识别章节、段落、时间跳转和地点变化。
- 在保留主要剧情走向的前提下，把 prose 改写成适合口播的旁白脚本。
- 语言应清晰、信息导向、口语友好、易于后续 TTS 或配音执行。
- 这一阶段不要输出视觉提示词、分镜提示词或资产清单。

### 步骤二

- 基于旁白脚本提炼生产用视觉节拍表。
- 一章通常会拆成多个 beat；不要把多个重大动作、重大认知变化或多个独立结果塞进一个 beat。
- 对每个 beat 明确其叙事功能、重要度、是否值得做完整 clip、建议镜头类型与镜头运动。
- 对每个 beat 增加 scene dramatization：最强画面核心、戏剧压力、连续性、最强静帧解释、最强运动解释、构图设计和镜头意图。
- beat 应像 storyboard planning unit，而不是 schema row；后续提示词从这些设计字段推导，而不是直接复制旁白。
- 输出可读 Markdown，并在文末附上且只附上一个可解析的 `json` 代码块，供共享运行时保存为 `02_beat_sheet.json`。

### 步骤三

- 基于旁白脚本和视觉节拍表提炼资产注册表。
- 资产提炼应围绕可复用性与一致性，而不是围绕单句 prose。
- 角色、场景、道具、车辆、服装/造型变体、年龄或状态变体都应按统一注册表方式管理。
- 输出可读资产文本，并在文末附上且只附上一个可解析的 `json` 代码块，供共享运行时保存为 `03_asset_registry.json`。

### 步骤四

- 基于节拍表和资产注册表生成 FLUX.2 klein 用关键帧提示词。
- 关键帧提示词必须是静帧构图导向，而不是视频动作描述。
- 应基于 `strongest_single_frame_interpretation`、`shot_design`、`camera_intent`、`dramatic_focus`、`visual_core` 和 `continuity_notes` 渲染一条强单帧场景提示词。
- 应强调主体、环境、主要物件、景别、构图、光线、可见状态、戏剧焦点、连续性与风格。
- 避免文学化抒情、主题总结、长篇情绪解释、多阶段动作、metadata list、字段机械拼接或把 prose 直接复制成提示词。
- `visual_style = 3D` 时默认使用 `anime_donghua_3d` 风格语言：cinematic donghua-inspired CG、anime-influenced 3D drama aesthetic、sharp silhouettes、elegant proportions、refined material rendering；避免 Pixar/Disney/toy-like/chibi/plush rounded family animation 漂移。
- 输出可读提示词清单，并在文末附上且只附上一个可解析的 `json` 代码块，供共享运行时保存为 `04_anchor_prompts.json`。

### 步骤五

- 基于节拍表、资产注册表和关键帧提示词生成 LTX-2 视频提示词。
- 默认关键帧已经建立主体、场景和风格，因此不要重新把整张画面完整描述一遍。
- 基于 `strongest_motion_interpretation`、`camera_intent`、`continuity_notes`、`emotional_pressure` 和对应锚帧的 visible state，写锚帧之后的自然运动延续。
- 重点写可见动作、环境运动、人物反应、镜头运动、节奏强弱和稳定性约束。
- 视频提示词应比关键帧提示词更短、更确定、更偏 motion-first。
- 对不适合做完整 clip 的 beat，可以跳过，或明确说明不生成视频提示词。
- 输出可读提示词清单，并在文末附上且只附上一个可解析的 `json` 代码块，供共享运行时保存为 `05_video_prompts.json`。
