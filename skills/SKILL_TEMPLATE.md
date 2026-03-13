---
name: your_skill_name
display_name: Your Skill Name
description: Describe what the workflow does and when a user should choose it from the shared runner.
supports_resume: false
input_extensions:
  - .txt
folder_mode: non_recursive

steps:
  - number: 1
    title: Main step
    default: true
    prompt_reference: main_prompt
    route_keywords_any:
      - keyword

runtime_inputs:
  - name: optional_input
    prompt: Enter a value
    type: string
    required: false
    step_numbers:
      - 1

references:
  - id: main_prompt
    path: references/main-prompt.md
    kind: prompt
    step_numbers:
      - 1

execution:
  strategy: step_prompt

output:
  mode: text
  filename_template: step_{step_number}_output.txt
  include_prompt_dump: true
---

# Skill Instructions

Use imperative instructions here. Keep the markdown body human-readable and workflow-focused.

## Guidance

- Treat this markdown body as the human source of truth.
- Keep detailed prompt text in `references/` files when possible.
- Prefer declarative `runtime_inputs`, `references`, and `steps` over engine changes.
- For report workflows, switch `execution.strategy` to `structured_report` and define `execution.stages`.
