# RECAP123

Shared multi-skill LLM runner for recap workflows.

## What Changed

The repository now has:

- one shared runtime engine in `engine/`
- one shared interactive entrypoint at `run.py`
- multiple workflow folders under `skills/`
- shared outputs under `outputs/<skill>/<timestamp>/`

Adding a normal new workflow should only require:

1. creating `skills/<new_skill>/`
2. adding `SKILL.md`
3. adding any files under `references/`

No new dedicated `run.py` or private engine package is required for standard skills.

## Run

From the repo root:

```bash
python run.py
```

The runner will:

1. print a brief introduction
2. show discovered skills
3. prompt for a skill
4. prompt for a `.txt` file or a folder of `.txt` files
5. execute the selected workflow
6. keep the session interactive so another job can be started without restarting

Folder processing is non-recursive and uses stable sorted order.

## Repository Layout

```text
RECAP123/
  run.py
  engine/
  skills/
    SKILL_TEMPLATE.md
    recap_analysis/
    recap_production/
  outputs/
  README.md
  tasks.md
  .env.example
```

## Skill Architecture

Each skill is driven by `SKILL.md` frontmatter plus human-readable instructions in the markdown body.

The shared engine currently supports two generic execution strategies:

- `step_prompt`
  For multi-step workflows where each step has its own prompt/reference file.
- `structured_report`
  For report-style workflows that run a configurable series of structured JSON stages and then render a final report.

### Supported `SKILL.md` metadata

- `name`
- `display_name`
- `description`
- `supports_resume`
- `input_extensions`
- `folder_mode`
- `steps`
- `runtime_inputs`
- `references`
- `execution`
- `output`

The markdown body remains the human source of truth for workflow behavior and guardrails. The frontmatter makes the workflow runnable by the shared engine.

## Standard Skill Template

Use [skills/SKILL_TEMPLATE.md](/c:/Users/CP/Documents/WORKSPACES/RECAP123/skills/SKILL_TEMPLATE.md) when adding a new skill.

Minimal flow for a new skill:

1. Copy `skills/SKILL_TEMPLATE.md` into `skills/<your_skill>/SKILL.md`.
2. Set the frontmatter fields.
3. Add any prompt or reference files under `skills/<your_skill>/references/`.
4. Run `python run.py` and choose the new skill from the menu.

## Runtime Inputs

Runtime inputs are driven by skill config, not hardcoded runner branches.

Examples already in use:

- `episode_count` for `recap_production` step 1
- `style` for `recap_production` step 2

Supported input types:

- `string`
- `int`
- `choice`
- `bool`

## Resume Behavior

Skills can opt into resume with `supports_resume: true`.

For resumable skills, the runner offers the latest unfinished state for that skill. State is stored in the output directory and includes:

- selected skill
- input path
- current step
- runtime inputs
- status
- output paths
- notes

For multi-step step-prompt workflows such as `recap_production`, a completed step can resume into the next step using the prior step output as the next input.

## Outputs

Outputs are written to:

```text
outputs/<skill_name>/<timestamp>/
```

Single-file runs write directly into that timestamp directory.

Folder runs also create:

```text
outputs/<skill_name>/<timestamp>/documents/<index>_<input_stem>/
```

Typical artifacts:

- `state.json`
- `prompt_dump.json`
- `stage_outputs.json` for structured workflows
- final `.txt` output

## Environment

The shared runtime loads `.env` from the repo root.

See `.env.example` for supported variables. The engine supports OpenRouter and OpenAI-compatible chat completions.

## Current Skills

- [skills/recap_analysis/SKILL.md](/c:/Users/CP/Documents/WORKSPACES/RECAP123/skills/recap_analysis/SKILL.md)
- [skills/recap_production/SKILL.md](/c:/Users/CP/Documents/WORKSPACES/RECAP123/skills/recap_production/SKILL.md)
