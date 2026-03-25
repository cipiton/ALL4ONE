---
name: rewriting
display_name: Rewriting
description: Multi-step rewriting, script polishing, and sanitization workflow for normalizing source material, planning replacements, producing a rewritten script, and running a final consistency pass.
supports_resume: true
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  aliases:
    - script_revision
    - script-revision
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
    qa_final_polish_model: strong

steps:
  - number: 1
    title: 读取并规范原稿
    description: Read the full source material, normalize naming/context, and produce a clean rewrite-ready source package.
    prompt_reference: step1_prompt
    write_to: normalized_source
    output_filename: 01_normalized_source.txt
    model_role: step_execution
    default: true
    input_blocks:
      - label: 【原始剧本/文本】
        from: user_brief
  - number: 2
    title: 生成替换与规避方案
    description: Build the sanitization and replacement plan before rewriting the script.
    prompt_reference: step2_prompt
    write_to: sanitization_plan
    output_filename: 02_sanitization_plan.txt
    model_role: step_execution
    input_blocks:
      - label: 【规范化原稿】
        from: normalized_source
  - number: 3
    title: 输出洗稿后剧本
    description: Apply the confirmed replacement strategy and produce the rewritten script draft.
    prompt_reference: step3_prompt
    write_to: revised_script_draft
    output_filename: 03_revised_script_draft.txt
    model_role: final_deliverable
    input_blocks:
      - label: 【规范化原稿】
        from: normalized_source
      - label: 【洗稿方案】
        from: sanitization_plan
  - number: 4
    title: 最终质检与统一
    description: Run the final QA pass and output the polished final revised script.
    prompt_reference: step4_prompt
    write_to: revised_script_final
    output_filename: 04_revised_script_final.txt
    model_role: qa_final_polish
    input_blocks:
      - label: 【洗稿方案】
        from: sanitization_plan
      - label: 【洗稿后剧本草稿】
        from: revised_script_draft

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
  - id: sensitive_words
    path: references/sensitive-words.md
    kind: reference
    step_numbers:
      - 2
      - 3
      - 4

execution:
  strategy: step_prompt

output:
  mode: text
  filename_template: "step_{step_number}_output.txt"
  include_prompt_dump: true
---

# Rewriting

Use this skill when the user wants rewriting, script polishing, washing, or sanitization on existing script-like text while preserving the story logic, structure, and dramatic readability.

## Shared Runtime Behavior

- The shared runtime starts from the selected step.
- Each step generates a draft, previews it, and waits for `Accept`, `Improve`, `Restart`, `View full`, or `Cancel`.
- Only accepted outputs are saved.
- After acceptance, the shared runtime automatically continues to the next step until the workflow ends or the user cancels.
- Resume is supported from the latest accepted step output.
- When the input is a coordinated script folder or a Skill 4 final adaptation plan, the runtime may switch into a shared project workflow that builds or reuses one refresh bible for the whole project before rewriting outputs.

## Refresh Bible Workflow

- Shared project mode supports:
  - `build_bible`
  - `rewrite_with_bible`
  - `build_bible_and_rewrite`
- The refresh bible is project-scoped and is meant to lock naming, term replacement, and consistency rules across a whole batch.
- A Skill 4 final adaptation plan is the primary canon source for the refresh bible.
- Script files can be added as supplemental evidence to enrich on-page terminology, alias usage, and practical naming examples.
- When a refresh bible already exists for the project, later rewrite runs should reuse it instead of inventing new rename rules.
- 默认命名策略是中文原名 -> 中文刷新名；除非用户明确要求其他语言，否则不要把中文人名、组织名、地点名、系统名、能力名、法宝名刷新成英文或拼音。
- 对主要角色与主要专有名词，默认不是“保留原名”，而是“刷新成新的中文规范名”；保留原名必须是例外，并且需要明确 preserve/lock 原因。
- 刷新圣经必须覆盖人物、称谓、关系标签、阵营/组织、地点、系统/契约/能力、法宝/关键道具、世界观专有名词、签名术语与禁用词。
- 在真实交付的 `final` 模式下，只使用刷新后的规范称呼，不输出 `新名（旧名）` 或中英混排主名；只有审校型 `audit` 模式才允许保留校对括注。
- 后续洗稿时，刷新圣经是项目级唯一规范来源；除非圣经明确允许，否则不要临时发明新名字，也不要混用原名和刷新名。
- 如果某个主要人物或主要名词最终没有被改名，必须记录明确的 preserve_reason，不能静默保持原样。

## Workflow

### Step 1: 读取并规范原稿

- Read the full source text.
- Normalize obvious formatting noise and naming inconsistencies without changing story meaning.
- Extract the rewrite-ready source package that later steps can rely on.

### Step 2: 生成替换与规避方案

- Identify names, places, institutions, key props, and sensitive vocabulary.
- Build the sanitization/replacement plan using the sensitive-word reference.
- Keep the plan practical, specific, and suitable for direct application in step 3.

### Step 3: 输出洗稿后剧本

- Apply the accepted plan to produce the rewritten script draft.
- Preserve pacing, scene order, dialogue function, and narrative clarity.
- Ensure the rewrite reads naturally rather than like mechanical string replacement.

### Step 4: 最终质检与统一

- Check the rewritten draft for consistency, completeness, and missed replacements.
- Fix terminology drift, naming mismatch, and awkward wording.
- Output the final revised script text only.

## Key Rules

- Always preserve the original plot logic unless the source itself is contradictory and must be normalized.
- Prioritize readability, consistency, and platform-safe wording.
- Sensitive-word handling must be context-aware, not purely literal.
- Keep replacements unified across the whole text.
- Do not output explanations, QA notes, or meta commentary in the final step.
- 中文项目默认采用中文到中文的刷新命名，贴合中文网文/短剧的角色气质、阵营层级和题材语感。
- 刷新不仅覆盖角色名，也必须覆盖组织、系统、能力、法宝、地点、身份标签和重复术语。
- 如果共享刷新圣经已经提供规范映射，后续步骤必须把它当作 source of truth 执行。
- 对主要人物名、主要势力名、主要系统/能力名、主要法宝名和主要地点名，默认应执行真正的中文 canon refresh，而不是仅做同名标准化。
