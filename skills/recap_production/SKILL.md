---
name: recap_production
display_name: Recap Production
description: Multi-step drama prep workflow for turning a synopsis or script `.txt` into a recap script, extracting assets, and generating an image-config text file.
supports_resume: true
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  startup:
    mode: explicit_step_selection
    default_step: 1
    allow_resume: true
    allow_auto_route: false
  execution:
    mode: sequential_with_review
    continue_until_end: false
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
- 步骤二基于剧本输出角色、场景、道具等资产及提示词。
- 步骤三基于资产结果输出生图配置文本。

## Step Rules

### 步骤一

- 从零创作时，需要询问集数。
- 如果输入明显是影视剧剧本改写任务，则不要再要求集数。
- 输出文本内容，等待共享评审流程中的接受、改进或重来决定。

### 步骤二

- 基于剧本进行资产提炼。
- 需要先确认资产风格：写实、2D、或 3D。
- 输出资产总清单和资产详情，等待共享评审流程中的接受、改进或重来决定。

### 步骤三

- 基于资产清单输出生图配置文本。
- 直接输出可保存的 txt 内容。
- 在共享评审流程中被接受后结束当前运行。
