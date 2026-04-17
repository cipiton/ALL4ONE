---
name: recap_analysis
display_name: Recap Analysis
description: Evaluate one or more novel `.txt` files for recap or audio-drama adaptation feasibility, including theme extraction, plot summary, adaptation scoring, episode-count recommendation, and audience fit.
supports_resume: false
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "Recap Analysis"
      zh: "解说适配分析"
    description:
      en: "Analyze one or more novel text files for recap or audio-drama adaptation feasibility."
      zh: "评估一个或多个小说文本是否适合做解说剧或有声改编。"
    workflow_hint:
      en: "This workflow reads the source, evaluates adaptation fit, recommends episode scale, and summarizes audience fit."
      zh: "此流程会先理解原文，再评估改编适配度、推荐集数规模，并总结受众匹配情况。"
    input_hint:
      en: "Skill 1 input: send one source `.txt` novel file, or a folder containing `.txt` novel files for batch analysis."
      zh: "第 1 个技能输入：请提供一个源 `.txt` 小说文件，或包含多个 `.txt` 小说文件的文件夹进行批量分析。"
    output_hint:
      en: "Writes a structured recap adaptation analysis report for each input file."
      zh: "会为每个输入文件生成结构化的解说剧适配分析报告。"
    starter_prompt:
      en: "Send the source novel `.txt` file or folder you want to evaluate."
      zh: "请提供要评估的源小说 `.txt` 文件或文件夹。"
  execution:
    mode: sequential_with_review
    preview_before_save: true
    save_only_on_accept: true

steps:
  - number: 1
    title: Generate evaluation report
    default: true

references:
  - id: adaptation_rules
    path: references/adaptation-rules.md
    kind: reference
    description: Rules for judging adaptation readiness and risks.
    stage_names:
      - adaptation_evaluation
  - id: episode_guidelines
    path: references/episode-guidelines.md
    kind: reference
    description: Episode-count guidance for recap pacing.
    stage_names:
      - episode_recommendation

execution:
  strategy: structured_report
  chunking:
    enabled: true
    threshold_chars: 18000
    chunk_size: 12000
    overlap: 1200
  stages:
    - name: structural_summary
      kind: document_json
      objective: 提取小说的主题、核心情节、人物设定、故事类型、基调，以及后续评估需要的基础认知。
      chunkable: true
      schema:
        story_title: string
        story_theme: string
        core_plot: string
        character_setup: string
        story_type: string
        tone: string
        plot_density: 高密度|中密度|低密度
        character_complexity: 复杂|中等|简单
        source_highlights:
          - string
        open_questions:
          - string
      merge_objective: 合并多个文本分块摘要，形成整本小说统一、稳定的结构化认知。
      merge_schema:
        story_title: string
        story_theme: string
        core_plot: string
        character_setup: string
        story_type: string
        tone: string
        plot_density: 高密度|中密度|低密度
        character_complexity: 复杂|中等|简单
        source_highlights:
          - string
        open_questions:
          - string
    - name: adaptation_evaluation
      kind: context_json
      objective: 依据改编规则评估适配度、风险、优势和优化建议。
      input_keys:
        - structural_summary
      reference_ids:
        - adaptation_rules
      schema:
        score_breakdown:
          plot_integrity: 0
          character_distinctiveness: 0
          theme_expression: 0
          narrative_adaptability: 0
          content_compliance: 0
        total_score: 0
        adaptation_level: 极高适配|高度适配|中度适配|低度适配|不适配
        strengths:
          - string
        risks:
          - string
        optimization_suggestions:
          - string
    - name: episode_recommendation
      kind: context_json
      objective: 依据集数指南，给出合理的解说剧集数范围与节奏说明。
      input_keys:
        - structural_summary
      reference_ids:
        - episode_guidelines
      schema:
        base_episode_estimate: string
        recommended_episode_range: string
        reasoning:
          - string
        pace_notes:
          - string
        assumptions:
          - string
    - name: audience_analysis
      kind: context_json
      objective: 分析目标受众、兴趣偏好、观看场景和受众匹配度。
      input_keys:
        - structural_summary
      schema:
        target_age_group: string
        interest_preferences:
          - string
        viewing_scenarios:
          - string
        audience_fit_explanation: string
    - name: final_report
      kind: context_json
      objective: 综合前序结果并整理为稳定的评估报告 sections。
      input_keys:
        - structural_summary
        - adaptation_evaluation
        - episode_recommendation
        - audience_analysis
      schema:
        sections:
          小说名称: string
          故事主题: string
          核心情节: string
          人物设定: string
          改编适配度评估: string
          推荐集数: string
          目标受众: string
          风险点: string
          结论: string

output:
  mode: section_report
  filename_template: "{input_stem}_analysis.txt"
  sections:
    - 小说名称
    - 故事主题
    - 核心情节
    - 人物设定
    - 改编适配度评估
    - 推荐集数
    - 目标受众
    - 风险点
    - 结论
  include_prompt_dump: true
---

# Skill Instructions

生成小说改编评估报告，并保持以下行为：

- 只接受 `.txt` 输入。
- 读取小说文本后，先建立稳定的结构化认知，再做规则评估和推荐。
- `references/adaptation-rules.md` 只在改编规则评估阶段使用。
- `references/episode-guidelines.md` 只在集数建议阶段使用。
- 最终输出是纯文本评估报告，不生成文档格式文件。
- 批量运行时，对每个文件单独产出报告，由共享引擎负责批处理与状态保存。

## Report Expectations

最终报告至少覆盖：

- 小说名称
- 故事主题
- 核心情节
- 人物设定
- 改编适配度评估
- 推荐集数
- 目标受众
- 风险点
- 结论
