---
name: recap_production
display_name: Recap Production
description: Multi-step drama prep workflow for turning a synopsis or script `.txt` into a recap script, extracting assets, generating an image-config text file, and planning episode-level video scenes.
supports_resume: true
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "Recap Production"
      zh: "解说剧制作"
    description:
      en: "Turn a synopsis or script text into a recap script, asset list, image-config output, and episode scene-planning package."
      zh: "将梗概或剧本文本转为解说剧剧本、资产清单、生图配置和分集视频场景规划包。"
    workflow_hint:
      en: "This workflow runs step by step: recap script, asset extraction, image config, then episode scene planning."
      zh: "此流程按步骤运行：先生成解说剧剧本，再提炼资产、输出生图配置，最后生成分集视频场景规划。"
    input_hint:
      en: "Skill 2 input: send a source `.txt` synopsis, novel excerpt, or script file to build the `02_recap_production/` bundle."
      zh: "第 2 个技能输入：请提供源 `.txt` 梗概、小说片段或剧本文件，用于生成 `02_recap_production/` 产物包。"
    output_hint:
      en: "Writes accepted recap-production outputs into `02_recap_production/`, keeping readable txt/md companions and canonical machine-readable JSON sidecars."
      zh: "会把已接受的解说剧步骤结果写入 `02_recap_production/`，同时保留便于阅读的 txt/md 文件，并生成规范的机器可读 JSON sidecar。"
    starter_prompt:
      en: "Send the source `.txt` synopsis, novel excerpt, or script for recap production."
      zh: "请提供用于解说剧制作的源 `.txt` 梗概、小说片段或剧本。"
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
    title: 输出解说剧剧本
    prompt_reference: step1_prompt
    write_to: recap_script
    output_filename: 01_recap_script.txt
    default: true
    route_keywords_any:
      - 梗概
      - 大纲
      - 简介
      - 故事
      - 设定
      - outline
      - synopsis
      - premise
    route_priority: 1
    input_blocks:
      - label: 【用户需求】
        from: user_brief
  - number: 2
    title: 提炼资产
    prompt_reference: step2_prompt
    write_to: extracted_assets
    output_filename: 02_assets.txt
    json_write_to: extracted_assets_json
    json_output_filename: 02_assets.json
    route_keywords_any:
      - 旁白
      - 对白
      - 台词
      - 分镜
      - script
      - narration
      - dialogue
      - 提炼资产
    requires_script_like: true
    input_blocks:
      - label: 【解说剧剧本】
        from: recap_script
  - number: 3
    title: 输出生图配置
    prompt_reference: step3_prompt
    write_to: image_config
    output_filename: 03_image_config.txt
    json_write_to: image_config_json
    json_output_filename: 03_image_config.json
    route_keywords_any:
      - 角色
      - 场景
      - 道具
      - 提示词
      - 音色
      - seed
      - 资产
      - 配置
      - asset
      - config
      - prompt
    requires_list_like: true
    input_blocks:
      - label: 【资产清单】
        from: extracted_assets
  - number: 4
    title: 输出视频场景脚本
    prompt_reference: step4_prompt
    write_to: episode_scene_script
    output_filename: 04_episode_scene_script.md
    json_write_to: episode_scene_script_json
    json_output_filename: 04_episode_scene_script.json
    route_keywords_any:
      - 视频
      - 分镜
      - 镜头
      - 场景脚本
      - 场景提示词
      - visual beat
      - scene beat
      - scene prompt
      - video
      - shot
    input_blocks:
      - label: 【解说剧剧本】
        from: recap_script
      - label: 【资产清单】
        from: extracted_assets
      - label: 【生图配置】
        from: image_config

runtime_inputs:
  - name: episode_count
    prompt: How many episodes should be planned?
    type: int
    required: true
    step_numbers:
      - 1
    min: 1
    max: 100
    skip_if_input_contains_any:
      - 影视剧剧本
      - 改写
      - rewrite
  - name: style
    prompt: Choose an asset style
    type: choice
    required: true
    step_numbers:
      - 2
    choices:
      - 写实
      - 2D
      - 3D

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

execution:
  strategy: step_prompt

output:
  mode: text
  filename_template: "step_{step_number}_output.txt"
  include_prompt_dump: true
---

# Skill Instructions

协助完成解说剧制作的前期文本准备工作，并保持以下规则：

- 从用户选择的起始步骤开始执行；共享运行时会在每一步生成草稿后先预览，再由用户选择接受、改进、重来、查看全文或取消。
- 只有用户接受的结果才会保存为当前步骤输出；一旦接受，共享运行时会自动继续到下一步，直到流程结束或用户取消。
- 如果运行被中断，共享引擎可基于最近一次已接受的步骤进行 resume。
- 步骤一输出解说剧剧本。
- 步骤二基于剧本先生成结构化资产对象，再渲染 `02_assets.txt`，并保存 `02_assets.json` 作为机器可读资产清单。
- 步骤三基于结构化资产对象生成结构化生图配置，再渲染 `03_image_config.txt`，并保存 `03_image_config.json` 作为机器可读生图配置。
- 步骤四基于剧本、资产和生图配置输出分集视频场景脚本，并额外保存 `04_episode_scene_script.json` 作为结构化场景规划包。

## Step Rules

### 步骤一

- 从零创作时，需要询问集数。
- 如果输入明显是影视剧剧本改写任务，则不要再要求集数。
- 输出文本内容，等待共享评审流程中的接受、改进或重来决定。

### 步骤二

- 基于剧本进行资产提炼。
- 需要先确认资产风格：写实、2D、或 3D；如果共享运行时已提供 `style`，则直接执行，不要再次询问。
- 先生成结构化资产数据，再输出资产总清单和资产详情文本，等待共享评审流程中的接受、改进或重来决定。

### 步骤三

- 基于结构化资产结果生成结构化生图配置。
- 输出可保存的 txt 内容时，应与对应 JSON 中的角色/场景/道具条目保持一致。
- 在共享评审流程中被接受后自动进入步骤四。

### 步骤四

- 基于步骤一到步骤三的结果生成 recap 视频用的分集视觉规划。
- 每集按有意义的视觉节拍拆成约 8-14 个 scene beat，不要逐句机械切分。
- 重点遵循 hook -> 核心推进 -> cliffhanger 的节奏组织方式。
- 每个 beat 都应同时作为视觉生成、旁白锚点和后续装配的共享规划单元。
- `anchor_text`、`priority`、`beat_role`、`pace_weight`、`asset_focus` 在实践中都应视为必填字段。
- `anchor_text` 必须短且可直接用于后续 narration/subtitle 对齐；`pace_weight` 只表示相对节奏，不表示真实时长。
- 相邻 beats 默认应保持人物、服装、地点和情绪连续性；镜头距离与机位运动应尽量避免机械重复。
- 输出可读 Markdown，并在文末附上可解析的唯一 `json` 代码块，供共享运行时保存为结构化场景规划文件。
- 保持故事与视觉规划导向，不要绑定最终 TTS 时长或逐秒时间轴。
