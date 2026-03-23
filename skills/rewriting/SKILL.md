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

steps:
  - number: 1
    title: 读取并规范原稿
    description: Read the full source material, normalize naming/context, and produce a clean rewrite-ready source package.
    prompt_reference: step1_prompt
    write_to: normalized_source
    output_filename: 01_normalized_source.txt
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
    input_blocks:
      - label: 【规范化原稿】
        from: normalized_source
  - number: 3
    title: 输出洗稿后剧本
    description: Apply the confirmed replacement strategy and produce the rewritten script draft.
    prompt_reference: step3_prompt
    write_to: revised_script_draft
    output_filename: 03_revised_script_draft.txt
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
