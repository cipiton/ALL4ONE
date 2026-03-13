# ONE4ALL

Shared multi-skill LLM runner for recap workflows.

## What Changed

The repository now has:

- one app-layer skill boundary in `app/skills/`
- one shared runtime engine in `engine/`
- one shared interactive entrypoint at `run.py`
- multiple workflow folders under `skills/`
- one registry file at `skills/registry.yaml` for exposed skills
- shared outputs under `outputs/<skill>/<timestamp>/`

Adding a normal new workflow should only require:

1. creating `skills/<new_skill>/`
2. adding `SKILL.md`
3. registering it in `skills/registry.yaml`
4. adding any files under `references/`

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
ONE4ALL/
  run.py
  app/
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

Phase 2 now separates app dispatch from engine execution:

- `skills/registry.yaml` is the preferred source of truth for which skills the app exposes.
- `app/skills/protocol.py` defines the normalized app-facing skill interface.
- `app/skills/catalog.py` loads the registry and instantiates adapters.
- `app/skills/adapters/` bridges the app layer to the current execution backend.
- each skill's `SKILL.md` remains the source of truth for runtime behavior, prompts, frontmatter, and references.

If `skills/registry.yaml` is present, the app loads skills from that registry through the catalog. If the registry is removed, the catalog falls back to the older `skills/*/SKILL.md` directory scan so current compatibility is retained.

Each skill is still driven by `SKILL.md` frontmatter plus human-readable instructions in the markdown body.

## Protocol, Catalog, Adapters

The app now talks to skills through a stable adapter boundary instead of reaching directly into skill folders from `run.py`.

- protocol:
  `app/skills/protocol.py` defines normalized concepts such as `SkillRunRequest`, `SkillRunResult`, resume points, and the common adapter interface.
- catalog:
  `app/skills/catalog.py` reads `skills/registry.yaml`, validates entries, resolves adapter names, instantiates adapters, and returns menu-friendly summaries.
- adapter:
  `app/skills/adapters/skill_md_adapter.py` is the generic Phase 2 bridge for current markdown-spec skills. It wraps the existing `SKILL.md` loading and shared engine execution flow instead of reimplementing it.

This is the key difference from Phase 1: the registry still decides what the app exposes, but the app now dispatches through adapters rather than directly coupling `run.py` to raw skill folders and engine-specific loading steps.

## Skill Registry

`skills/registry.yaml` is a small manifest that explicitly lists the skills available to the app.

In Phase 2, each entry points at an existing `SKILL.md` and declares which adapter should handle it:

```yaml
version: 1
skills:
  - id: recap_analysis
    type: skill
    adapter: skill_md
    spec_path: skills/recap_analysis/SKILL.md
    enabled: true
```

Registry responsibilities:

- decide whether a skill is exposed in the menu
- provide a stable registration id
- declare which adapter should execute the skill
- point the engine at the skill spec file

`SKILL.md` responsibilities:

- define execution behavior
- define frontmatter such as `steps`, `references`, `runtime_inputs`, `execution`, and `output`
- provide the human-readable workflow instructions

Phase 2 adds the adapter boundary, but does not add cross-skill workflows or replace the `SKILL.md` parser. The shared engine remains the execution backend.

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

Use `skills/SKILL_TEMPLATE.md` when adding a new skill.

Minimal flow for a new skill:

1. Copy `skills/SKILL_TEMPLATE.md` into `skills/<your_skill>/SKILL.md`.
2. Set the frontmatter fields.
3. Add a registry entry to `skills/registry.yaml` that points to `skills/<your_skill>/SKILL.md`.
4. Set `adapter: skill_md` for standard markdown-spec skills.
5. Add any prompt or reference files under `skills/<your_skill>/references/`.
6. Run `python run.py` and choose the new skill from the menu.

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

- `recap_analysis` via `skills/registry.yaml` -> `skills/recap_analysis/SKILL.md`
- `recap_production` via `skills/registry.yaml` -> `skills/recap_production/SKILL.md`
