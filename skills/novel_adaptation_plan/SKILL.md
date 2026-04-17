---
name: novel_adaptation_plan
display_name: Novel Adaptation Plan
description: AI短剧工业化改编策划，根据小说原文或已归纳母本自动完成名场面提取分级、5阶段节奏规划、单集名场面绑定，并输出标准化短剧改编方案。
supports_resume: true
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  aliases:
    - short_drama_adaption
    - short-drama-adaption
  i18n:
    display_name:
      en: "Novel Adaptation Plan"
      zh: "小说改编计划"
    description:
      en: "Industrial short-drama adaptation planning workflow for novels or prepared master outlines."
      zh: "面向小说或已归纳母本的工业化短剧改编策划流程。"
    workflow_hint:
      en: "This workflow extracts set pieces, grades them, plans pacing, binds episodes, and writes the final adaptation package."
      zh: "此流程会提取并分级名场面，规划节奏阶段，绑定单集安排，并输出最终改编方案。"
    input_hint:
      en: "Novel Adaptation Plan input: send one `.txt` novel file, prepared outline/master outline, or project-ingested dossier for adaptation planning."
      zh: "小说改编计划输入：请提供一个 `.txt` 小说文件、已整理大纲/母本，或项目归纳档案来生成改编方案。"
    output_hint:
      en: "Writes the standardized short-drama adaptation package and supporting planning files."
      zh: "会生成标准化短剧改编方案及配套规划文件。"
    starter_prompt:
      en: "Send the novel source `.txt`, prepared outline, or project dossier for adaptation planning."
      zh: "请提供用于改编策划的小说源 `.txt`、已整理大纲或项目档案。"
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
  model_routing:
    step_execution_model: fast
    final_deliverable_model: strong
    project_master_outline_model: strong
system_instructions: |
  If source_mode=project_ingested or source_type=synthesized_master_outline, treat the provided dossier as sufficient working source material.
  In that case, operate in best-effort production mode:
  - do not ask the user to confirm missing inputs
  - do not output a questionnaire, checklist, or requirements request
  - make conservative assumptions where details are missing
  - produce a substantive adaptation plan directly
  Default to a 60-episode vertical short-drama structure when no explicit episode count is provided.
  Infer the novel genre, approximate original word count, and episode count if the source does not state them explicitly.
  The final output must follow the skill's standardized table format exactly.
  Preserve the original two-table adaptation-plan handoff intact, then extend it with a practical character-bible annex for downstream script generation.
  In project-ingested mode, actively surface character-registry information from the synthesized dossier instead of omitting it.
  Only mention blockers briefly at the end if generation is truly impossible; blockers must never replace the deliverable.

steps:
  - number: 1
    id: intake_and_preparation
    title: 信息确认与准备
    description: Read the full source, infer or confirm the core project inputs, and prepare a unified adaptation working brief.
    prompt_reference: step1_prompt
    write_to: adaptation_brief
    output_filename: 01_adaptation_brief.txt
    model_role: step_execution
    default: true
    input_blocks:
      - label: 【原始小说/母本档案】
        from: user_brief
  - number: 2
    id: set_piece_extraction
    title: 名场面提取
    description: Extract strong set pieces from the source according to the original industrial short-drama adaptation rules.
    prompt_reference: step2_prompt
    write_to: set_piece_candidates
    output_filename: 02_set_piece_candidates.txt
    model_role: step_execution
    input_blocks:
      - label: 【改编工作底稿】
        from: adaptation_brief
  - number: 3
    id: set_piece_grading
    title: 名场面分级
    description: Grade extracted set pieces into S/A/B/C based on the original scoring criteria and landing rules.
    prompt_reference: step3_prompt
    write_to: graded_set_pieces
    output_filename: 03_graded_set_pieces.txt
    model_role: step_execution
    input_blocks:
      - label: 【改编工作底稿】
        from: adaptation_brief
      - label: 【名场面候选】
        from: set_piece_candidates
  - number: 4
    id: five_phase_pacing
    title: 5阶段节奏规划
    description: Plan the five adaptation phases using the original percentage split and pacing logic.
    prompt_reference: step4_prompt
    write_to: phase_pacing_plan
    output_filename: 04_phase_pacing_plan.txt
    model_role: step_execution
    input_blocks:
      - label: 【改编工作底稿】
        from: adaptation_brief
      - label: 【名场面分级结果】
        from: graded_set_pieces
  - number: 5
    id: episode_binding
    title: 单集名场面绑定
    description: Bind the graded set pieces into episode-level progression with hook endings and production labels.
    prompt_reference: step5_prompt
    write_to: episode_binding_plan
    output_filename: 05_episode_binding_plan.txt
    model_role: step_execution
    input_blocks:
      - label: 【改编工作底稿】
        from: adaptation_brief
      - label: 【名场面分级结果】
        from: graded_set_pieces
      - label: 【5阶段节奏规划】
        from: phase_pacing_plan
  - number: 6
    id: standardized_output
    title: 输出标准化方案
    description: Deliver the final standardized short-drama adaptation package in the original two-table format.
    prompt_reference: step6_prompt
    write_to: final_adaptation_plan
    output_filename: 06_final_adaptation_plan.txt
    model_role: final_deliverable
    input_blocks:
      - label: 【改编工作底稿】
        from: adaptation_brief
      - label: 【名场面分级结果】
        from: graded_set_pieces
      - label: 【5阶段节奏规划】
        from: phase_pacing_plan
      - label: 【单集名场面绑定方案】
        from: episode_binding_plan

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
  - id: step6_prompt
    path: references/step6-prompt.md
    kind: prompt
    step_numbers:
      - 6

execution:
  strategy: step_prompt

output:
  mode: text
  filename_template: "step_{step_number}_output.txt"
  include_prompt_dump: true
---

# AI短剧工业化改编策划

## 任务目标
- 本技能用于：根据小说原文或已归纳母本，一键完成AI短剧工业化改编策划
- 能力包含：名场面提取与分级、5阶段节奏规划、单集名场面绑定、标准化制作方案输出
- 触发条件：用户需要将小说改编为竖屏短剧，并希望得到可直接用于后续生产的标准方案

## 共享运行方式

- 运行时从所选步骤开始执行
- 每一步会先生成草稿，再等待 `Accept`、`Improve`、`Restart`、`View full` 或 `Cancel`
- 只有被接受的结果才会保存
- 接受后会自动继续执行下一步，直到流程结束或用户取消
- 支持从最近一次已接受的步骤继续运行

## 项目归纳模式

- 当输入带有 `source_mode: project_ingested` / `source_type: synthesized_master_outline` 时，将归纳后的项目档案视为正式母本
- 该模式下直接按最佳努力输出，不回退到问卷、确认单或补资料请求
- 如果原始资料没有明确总集数，默认按 `60集` 竖屏短剧方案处理，并在输出中自然说明该假设

## 前置准备
- 无需额外依赖
- 默认完整阅读用户提供的小说原文、归纳母本或项目档案

## 操作步骤
1. **信息确认与准备**
   - 确认或推断3项基础信息：小说题材、原文字数、自定义总集数（默认60集）
   - 接收并完整阅读小说原文或归纳母本
   - 如果缺少显式字段，则依据内容作保守推断，不中断流程

2. **名场面提取**
   - 从原文中识别连续500-1500字的高价值片段
   - 筛选满足至少1条以下特征的片段：
     - 强冲突 / 对抗 / 打脸 / 对峙
     - 剧情反转 / 真相揭露 / 身份曝光
     - 人设高光 / 关键抉择 / 情绪极值
     - 可传播金句 / 标志性仪式场景（告白、决战、决裂等）
     - 主线不可逆关键节点
     - 幽默风趣、具备强传播特性的梗

3. **名场面分级**
   - S级：≥3条特征，主线终极节点 / 全局反转 / 极致情绪，1个=1集
   - A级：≥2条特征，主线关键节点 / 中强高光，1-2个=1集
   - B级：≥1条特征，爽点 / 情绪 / 主线高潮，2-3个=1集
   - C级：无上述特征，纯过渡，仅做衔接，不占名场面名额

4. **5阶段节奏规划**
   - 开篇钩子期：10%集数
   - 主线铺垫期：20%集数
   - 高潮密集期：40%集数
   - 终极爆发期：20%集数
   - 结局留钩期：10%集数
   - 集数按四舍五入取整，保证总和等于最终总集数

5. **单集名场面绑定**
   - 每集必含：冲突 / 反转 / 情绪峰值 三选一
   - 每集结尾：强制留钩子（悬念 / 爽点预告 / 伏笔）
   - S级名场面必须落地：优先放在开篇、付费点、终极高潮位
   - 过渡剧情总占比≤10%，不水剧情

6. **输出标准化方案**
   - 严格按照指定格式先输出两个原始核心表格
   - 在不破坏原始表格结构和用途的前提下，追加角色圣经与人物驱动说明
   - 确保内容无废话、可直接导入AI生产工具，并能直接交接给下游剧本生成

## 输出格式

### 表1：阶段集数规划表
| 阶段         | 阶段定位                | 规划集数 | 名场面配比建议（S/A/B） | 核心节奏要求                | 关键功能                  |
|--------------|-------------------------|----------|-------------------------|-----------------------------|---------------------------|
| 开篇钩子期   | 强冲突留人              |          |                         | 开篇炸点，高留存            | 引流/抓用户               |
| 主线铺垫期   | 立人设+铺世界观         |          |                         | 节奏平稳，埋线索            | 铺垫主线                  |
| 高潮密集期   | 名场面高密度连环        |          |                         | 高爽高密，持续上头          | 核心付费/流量段           |
| 终极爆发期   | 主线反转&S级集中        |          |                         | 情绪拉满，终极高潮          | 剧情核心爆点              |
| 结局留钩期   | 收尾+埋第二季钩子       |          |                         | 闭环留悬念，引导续看        | 留客/第二季铺垫           |
| 合计         | ——                      |          | ——                      | ——                          | 适配AI批量制作            |

### 表2：单集剧情+名场面绑定详细大纲
| 集数 | 所属阶段     | 名场面等级 | 绑定名场面（原文核心内容） | 单集纯剧情概要（50-100字） | 节奏亮点 | 结尾钩子 | 制作标注（引流/付费/过渡） |
|------|--------------|------------|----------------------------|----------------------------|----------|----------|----------------------------|
| 1    |              |            |                            |                            |          |          |                            |
| 2    |              |            |                            |                            |          |          |                            |
| ...  |              |            |                            |                            |          |          |                            |
| 总计 | ——           | ——         | S__个 / A__个 / B__个      | 总纯剧情字数：________     | ——       | ——       | 100%适配AI工业化生成       |

### 附录：角色圣经与人物驱动说明
- 保留前两张表不变后，再追加此附录
- 附录需至少包含：
  - 核心人物设定与关系
  - 核心关系网与改编强化建议
  - 人物-阶段 / 人物-集段分配说明
- 目标是让下游 `Novel-to-Drama Script` 明确知道谁驱动冲突、谁承接情绪、谁在何处推进或反转

## 最终校准要求
1. 总集数严格等于最终总集数，不增减
2. 所有S/A级名场面100%落地，无遗漏
3. 阶段比例、节奏、钩子完全符合竖屏短剧规则
4. 输出内容无废话、可直接导入AI生产工具
5. 附录中的角色圣经必须足够支撑下游剧本生成，不能只停留在泛泛文学分析

## 单集制作标准
- 时长：60-90秒/集
- 单集纯剧情字数：800-1200字
- 每集必含冲突 / 反转 / 情绪峰值三选一
- 每集结尾强制留钩子

## 注意事项
- 充分利用对文本内容的深度理解能力，精准识别名场面
- 严格按照规则执行，确保输出标准化、可直接用于AI生产
- 在名场面提取和分级时，结合小说题材特点进行判断
- 确保阶段节奏符合竖屏短剧的流量和留存规律
