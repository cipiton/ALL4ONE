---
name: novel2script
description: end-to-end workflow for chinese ai short drama / vertical microdrama creation. use when the user wants to turn an idea, premise, novel excerpt, character profile, episode outline, or draft script into story polish, episode plot, highlight beats, per-episode screenplay, script analysis, production asset extraction, or asset image config; supports full pipeline or any single step with iterative revisions.
metadata:
  display_name: Novel 2 Script
  i18n:
    display_name:
      en: "Novel 2 Script"
      zh: "小说转剧本"
    description:
      en: "End-to-end short-drama creation workflow from source material to script, analysis, and assets."
      zh: "从源素材一路推进到剧本、分析和资产的完整短剧创作流程。"
    workflow_hint:
      en: "Choose the starting step in chat and continue through the pipeline one approved step at a time."
      zh: "可在对话中选择起始步骤，并按已确认的步骤逐步推进整条流程。"
    input_hint:
      en: "Novel 2 Script input: send source material as a `.txt` file, a folder of `.txt` files, or a direct story brief when starting from an idea."
      zh: "小说转剧本输入：请提供 `.txt` 源素材文件、包含 `.txt` 的文件夹；如果从创意开始，也可直接输入故事需求。"
    output_hint:
      en: "Writes step-by-step short-drama production deliverables such as outline, highlights, scripts, analysis, and assets."
      zh: "会按步骤生成短剧生产结果，例如大纲、亮点、剧本、分析和资产文件。"
    starter_prompt:
      en: "Send the source material, folder, or direct brief for the novel-to-script workflow."
      zh: "请提供小说转剧本流程所需的源素材、文件夹或直接创意需求。"
  supports_resume: true
  input_extensions:
    - .txt
  folder_mode: recursive
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
---

# novel2script: short drama creation pipeline

## what this skill does
Convert raw story material (idea / synopsis / novel excerpt / outline / draft script) into production-ready short-drama deliverables:
1) polished story, 2) episode plot, 3) highlight beats (爽点/反转/打脸/悬念), 4) per-episode screenplay for vertical microdrama, 5) script analysis, 6) production asset extraction, 7) plain-text asset image configuration.

This skill is designed to run **either the full pipeline** or **a single requested step**.

This skill runs through the shared skill-driven architecture under the `novel2script` skill id.

## runtime output files
When the shared runtime executes this workflow, persist every available step output as UTF-8 plain text under the shared `outputs/novel2script/` run directory. Reuse the same stable filenames when a step is rerun or revised in the same run directory.

- step 1 `story` -> `01_story.txt`
- step 2 `episode_outline` -> `02_episode_outline.txt`
- step 3 `highlights` -> `03_highlights.txt`
- step 4 `episode_scripts` -> `04_episode_scripts.txt`
- step 5 `analysis` -> `05_analysis.txt`
- step 6 `assets` -> `06_assets.txt`
- step 7 `asset_image_config` -> `07_asset_image_config.txt`

## start here: intake + routing (always do first)
1. Identify what the user already has and what they want next.
   - Ask **one** short question if unclear: “what do you have right now (idea / story / episode outline / script / asset list), and what do you need next?”
2. If the user explicitly requests a step (e.g., “step 4”, “write episode scripts”, “extract assets”), run that step.
3. Otherwise, pick the next logical step using the routing rules below.
4. Ask only the **minimum** missing parameters required for the chosen step (max **3** questions in a single message).
5. Default output language is **chinese** unless the user asks otherwise.

## global operating rules (must follow)
- **one step at a time**: never execute multiple steps in one response.
- **no auto-advance**: after finishing a step, stop and ask the user to either:
  - approve and continue (e.g., “approved, go to step 2”), or
  - request revisions, or
  - jump to another step.
- **revision loop**: if the user requests changes, stay on the current step and iterate until they approve.
- **minimum follow-ups**: do not interrogate the user; ask only what is necessary to produce a good output for the current step.
- **keep continuity internally**: maintain an internal “canon” (genre, core conflict, key characters, episode count, tone constraints). Only restate it in the answer if the user asks for a recap.
- **respect hard constraints** (from the step prompt files): strong conflict, strong emotion, no villain redemption / no moralizing filler, maintain character consistency.
- **do not add scripts**: this is a creative workflow; do not propose coding solutions.

## routing rules (how to choose the correct step)
Choose the step using the user’s explicit request first; if not explicit, infer from what they provided:

- **step 1** (完善故事 / story polish): user provides only an idea, premise, hook, logline, or a rough novel excerpt and wants “a complete story”.
- **step 2** (分集剧情 / episode plot): user has a complete story/synopsis (or you produced step 1) and wants an episode-by-episode plot.
- **step 3** (亮点梳理 / highlights): user has episode plots and wants highlight beats (爽点/反转/打脸/悬念) mapped to episodes.
- **step 4** (分集剧本 / episode screenplay): user has episode plots (or wants direct adaptation) and needs vertical microdrama screenplay scenes.
- **step 5** (剧本分析 / analysis): user has screenplay(s) and wants feasibility/market/arc analysis.
- **step 6** (资产提炼 / asset extraction): user has screenplay(s) and wants assets (角色/场景/道具) + image prompts.
- **step 7** (资产生图配置 / image config): user already has step 6 output and needs the strict plain-text config export.

### dependency notes
- step 3 depends on step 2.
- step 5 and step 6 depend on step 4.
- step 7 depends on step 6.

## step playbooks

### step 1: 完善故事 (story polish)
- Read: `prompts/step1-story-perfect.md`.
- Produce:
  - **概述内容** must include: 核心概念、故事类型、核心主题、主要人物（主角/配角/反派）
  - **完整故事**: 500–1000 chinese characters (unless the user asks for another length)
  - Emphasize: **strong contradiction + strong conflict**, escalating stakes, 2–3 “名场面”.
- End by asking for approval or revisions. Do **not** proceed to step 2 automatically.

### step 2: 分集剧情 (episode plot)
- Read: `prompts/step2-episode-plot.md`.
- Minimum required inputs:
  - episode count (ask if missing)
  - target per-episode length (default: 1–2 minutes, unless user specifies)
- Output requirements:
  - produce episode-by-episode plot; episode 1 must front-load the most intense conflict and create a hook.
  - follow the structure shown in `assets/fractional-plot-reference.docx` (open and mimic its headings if needed).
- End by asking for approval or revisions.

### step 3: 亮点梳理 (highlights)
- Read: `prompts/step3-highlights.md`.
- Input: episode plot from step 2.
- Produce:
  - per-episode highlight beats, clearly labeled (爽点/反转/打脸/悬念)
  - note which episode/beat is the strongest hook to front-load in episode 1.
- End by asking for approval or revisions.

### step 4: 分集剧本 (episode screenplay)
- Read: `prompts/step4-episode-script.md`.
- Inputs:
  - episode plot (preferred), or a clear story synopsis + user confirmation to adapt directly.
  - episode count + target runtime constraints.
- Hard constraints:
  - **10–12 storyboard groups (分镜组) per episode**
  - **1–2 minutes per episode**
  - episode 1: first 30 seconds must contain the strongest hook / conflict / suspense.
- Output format:
  - follow `assets/fractional-drama-reference.docx` (open and mimic if needed).
  - keep each storyboard group explicit: 场景/人物/动作画面/对白/情绪节奏 (align with your reference format).
- End by asking for approval or revisions.

### step 5: 剧本分析 (script analysis)
- Read: `prompts/step5-script-analysis.md`.
- Input: episode screenplay(s).
- Produce structured analysis:
  - production feasibility (ai drama constraints)
  - market positioning + hook strength
  - character arc and motivation consistency
  - pacing and escalation
  - risk list + improvement suggestions
- End by asking for approval or revisions.

### step 6: 资产提炼 (asset extraction)
- Read: `prompts/step6-asset-extraction.md`.
- Input: episode screenplay(s) (step 4 output).
- Output requirements (strict):
  1. first output a **total asset list** (角色 / 场景 / 道具), matching what you will output in detail.
  2. then output **detailed assets** in the order: 角色 → 场景 → 道具.
  3. naming rules:
     - default character look: `角色名`
     - extra character look: `角色名_造型名`
  4. image prompt structure (keep consistent): 风格及光线 / 输出要求 / 主体内容.
  5. **voice spec is mandatory for every default character look**:
     - must exist, must match the asset name, must include seed.
     - verify completeness at the end internally before responding.
- End by asking for approval or revisions.

### step 7: 资产生图配置 (plain-text image config)
- Read: `prompts/step7-asset-image-config.md`.
- Input: step 6 asset extraction output.
- Hard constraints (absolute):
  - output **plain text only** (no markdown, no headings, no explanations)
  - do not add extra blank lines (“不要自动隔行”)
  - copy content from step 6 without rewriting
  - ensure every default character has its matching “音色” block
  - order must be 角色 → 场景 → 道具; numbering must restart from 1 in each section.
- Formatting reference:
  - use the txt template inside `assets/` as the exact formatting reference.
  - use `assets/asset-template.txt` as the exact plain-text formatting template.
- Important: after producing step 7 output, **do not** append any follow-up text.

## resources
- step instructions: `prompts/` (one file per step)
- formatting references: `assets/` (docx/txt templates)

## usage examples
- full pipeline: “i have an idea for a rebirth revenge microdrama; take me from story polish to screenplay, then extract assets.”
- single step: “here is my episode plot. jump to step 4 and write the per-episode screenplay.”

## step registry
```skill-registry
version: 1
entrypoint: step1
supports_resume: true
intake:
  enabled: true
  file_prompt: "file input: "
  user_prompt: "user prompt: "
  router_prompt: prompts/router-intake.md
  max_router_chars: 12000
  recursive_txt_search: true
llm:
  model_env: OPENAI_MODEL
  temperature_env: OPENAI_TEMPERATURE
  max_output_tokens_env: OPENAI_MAX_OUTPUT_TOKENS
  timeout_env: OPENAI_TIMEOUT
  instructions: You are a senior Chinese vertical microdrama writer. Follow the current step prompt exactly and preserve continuity across steps.
runtime_inputs:
  - name: episode_count
    prompt: How many episodes should be planned?
    type: int
    required: true
    step_ids:
      - step2
      - step4
    min: 1
    max: 200
  - name: episode_runtime
    prompt: Target per-episode runtime
    type: string
    required: false
    default: 1-2分钟
    step_ids:
      - step2
      - step4
references:
  - id: plot_reference
    path: assets/fractional-plot-reference.docx
    kind: reference
    step_ids:
      - step2
  - id: drama_reference
    path: assets/fractional-drama-reference.docx
    kind: reference
    step_ids:
      - step4
  - id: asset_template
    path: assets/asset-template.txt
    kind: reference
    step_ids:
      - step7
  - id: asset_spreadsheet
    path: assets/资产提炼生图配置.xlsx
    kind: reference
    step_ids:
      - step6
      - step7
steps:
  - id: step1
    title: 完善故事
    prompt: prompts/step1-story-perfect.md
    write_to: story
    output_filename: 01_story.txt
    route_keywords_any:
      - step1
      - step 1
      - 完善故事
      - idea
      - premise
      - logline
      - novel
      - 小说
      - 梗概
    route_priority: 1
    input_blocks:
      - label: 【用户需求】
        from: user_brief
    approval:
      required: true
      preview_from: story
    next: step2
  - id: step2
    title: 分集剧情
    prompt: prompts/step2-episode-plot.md
    write_to: episode_outline
    output_filename: 02_episode_outline.txt
    route_keywords_any:
      - step2
      - step 2
      - 分集剧情
      - episode plot
      - episode outline
      - outline
      - 分集大纲
    route_priority: 1
    input_blocks:
      - label: 【故事大纲】
        from: story
    approval:
      required: true
      preview_from: episode_outline
    next: step3
  - id: step3
    title: 亮点梳理
    prompt: prompts/step3-highlights.md
    write_to: highlights
    output_filename: 03_highlights.txt
    route_keywords_any:
      - step3
      - step 3
      - 亮点
      - highlights
      - 爽点
      - 反转
      - 悬念
    route_priority: 1
    input_blocks:
      - label: 【分集剧情】
        from: episode_outline
    approval:
      required: true
      preview_from: highlights
    next: step4
  - id: step4
    title: 分集剧本
    prompt: prompts/step4-episode-script.md
    write_to: episode_scripts
    output_filename: 04_episode_scripts.txt
    route_keywords_any:
      - step4
      - step 4
      - 分集剧本
      - screenplay
      - script
      - 剧本
      - 分镜
    route_priority: 2
    requires_list_like: true
    input_blocks:
      - label: 【分集剧情】
        from: episode_outline
      - label: 【亮点】
        from: highlights
        required: false
    approval:
      required: true
      preview_from: episode_scripts
    next: step5
  - id: step5
    title: 剧本分析
    prompt: prompts/step5-script-analysis.md
    write_to: analysis
    output_filename: 05_analysis.txt
    route_keywords_any:
      - step5
      - step 5
      - 剧本分析
      - analysis
      - 市场分析
      - 可行性
    route_priority: 2
    requires_script_like: true
    input_blocks:
      - label: 【剧本】
        from: episode_scripts
    approval:
      required: true
      preview_from: analysis
    next: step6
  - id: step6
    title: 资产提炼
    prompt: prompts/step6-asset-extraction.md
    write_to: assets
    output_filename: 06_assets.txt
    route_keywords_any:
      - step6
      - step 6
      - 资产提炼
      - assets
      - 角色
      - 场景
      - 道具
      - 生图提示词
    route_priority: 2
    requires_script_like: true
    input_blocks:
      - label: 【剧本】
        from: episode_scripts
      - label: 【分析】
        from: analysis
        required: false
    approval:
      required: true
      preview_from: assets
    next: step7
  - id: step7
    title: 资产生图配置
    prompt: prompts/step7-asset-image-config.md
    write_to: asset_image_config
    output_filename: 07_asset_image_config.txt
    route_keywords_any:
      - step7
      - step 7
      - 资产生图配置
      - image config
      - 生图配置
      - config
    route_priority: 3
    requires_list_like: true
    input_blocks:
      - label: 【步骤六资产提炼内容】
        from: assets
    approval:
      required: false
      preview_from: asset_image_config
    next: END
```
