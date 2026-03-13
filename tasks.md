# Refactor Tasks

- [x] Audit the two existing runtimes and separate shared engine concerns from skill-specific behavior.
  Evidence: reviewed both old `run.py` entrypoints, duplicated engine modules, both `SKILL.md` files, and the per-skill tasks/readmes before refactoring.
- [x] Create a shared root `engine/` package and root `run.py`.
  Evidence: added `engine/models.py`, `engine/skill_loader.py`, `engine/input_loader.py`, `engine/planner.py`, `engine/router.py`, `engine/prompts.py`, `engine/executor.py`, `engine/writer.py`, `engine/state_store.py`, `engine/terminal_ui.py`, `engine/llm_client.py`, and root `run.py`.
- [x] Move skills under repo-root `skills/` and make `SKILL.md` the runtime control plane.
  Evidence: both workflows now live under `skills/recap_analysis/` and `skills/recap_production/`, and their `SKILL.md` files include machine-readable frontmatter plus human-readable instructions.
- [x] Replace hardcoded workflow prompts with declarative skill-driven runtime inputs and references.
  Evidence: `runtime_inputs` and `references` are parsed from skill metadata; `episode_count` and `style` are no longer hardcoded in the runner.
- [x] Unify state, outputs, and resume behavior under root `outputs/`.
  Evidence: the shared writer/state modules create `outputs/<skill>/<timestamp>/...`, save `state.json`, and resume from the latest incomplete state for resumable skills.
- [x] Support single-file and folder execution from the shared runner.
  Evidence: the root runner accepts either one `.txt` file or a non-recursive folder of `.txt` files and processes folder contents in stable sorted order.
- [x] Preserve both current skills with shared engine strategies instead of separate apps.
  Evidence: `recap_production` uses the shared `step_prompt` strategy and `recap_analysis` uses the shared `structured_report` strategy.
- [x] Add onboarding guidance for future skills.
  Evidence: added `skills/SKILL_TEMPLATE.md` and updated `README.md` with the new architecture and new-skill workflow.
- [x] Run sanity checks for imports, startup, and skill discovery.
  Evidence: `python -m compileall run.py engine skills` passed; `echo 0|python run.py` started successfully and showed the interactive menu with `Recap Analysis` and `Recap Production`; smoke runs completed for analysis, production step 1, and production resume into step 2 under root `outputs/`.
- [x] Add `skills/registry.yaml` as the Phase 1 registration manifest.
  Evidence: added `skills/registry.yaml` with explicit enabled entries for `recap_analysis` and `recap_production`.
- [x] Update skill discovery to prefer the registry and validate entries clearly.
  Evidence: `engine/skill_loader.py` now loads `skills/registry.yaml` first, validates `id`/`type`/`spec_path`, resolves spec paths from repo root, and then loads each enabled skill through the existing `load_skill(...)` flow.
- [x] Retain fallback compatibility with legacy directory scanning.
  Evidence: after temporarily renaming `skills/registry.yaml`, `echo 0|python run.py` still started and showed both skills from `skills/*/SKILL.md`, then the registry file was restored.
- [x] Update documentation for Phase 1 registry usage.
  Evidence: `README.md` now explains the registry purpose, its difference from `SKILL.md`, how to add a new skill in Phase 1, and that the registry is the preferred exposure point.
- [x] Add an app-level skill protocol for normalized execution and resume handling.
  Evidence: added `app/skills/protocol.py` with `SkillAdapter`, `SkillRunRequest`, `SkillResumeRequest`, `SkillResumePoint`, and normalized result models.
- [x] Add a registry-backed skill catalog that resolves adapters.
  Evidence: added `app/skills/catalog.py`, which loads `skills/registry.yaml`, validates `id`/`type`/`adapter`/`spec_path`, instantiates adapters, and exposes `list_skills()`, `get_skill()`, and `menu_summaries()`; a direct catalog probe returned both registered skills with registry-provided descriptions.
- [x] Add a generic `skill_md` adapter that bridges the app layer to the current engine.
  Evidence: added `app/skills/adapters/skill_md_adapter.py`, which loads the existing `SKILL.md`, calls `execute_input_paths(...)`, and normalizes run/resume results for the app layer.
- [x] Refactor `run.py` to dispatch through the catalog and adapter boundary.
  Evidence: `run.py` now loads `SkillCatalog`, shows menu summaries from the catalog, prompts for input, and executes `run(...)` or `resume(...)` on the selected adapter instead of calling engine skill folders directly.
- [x] Update the registry schema for adapter-based dispatch.
  Evidence: `skills/registry.yaml` now declares `adapter: skill_md` for both current skills.
- [x] Verify Phase 2 imports, startup, and adapter-backed discovery.
  Evidence: `python -m compileall run.py app engine skills` passed; `echo 0|python run.py` started successfully and showed both skills through the new catalog/adapter path; after temporarily renaming `skills/registry.yaml`, `echo 0|python run.py` still started and showed both skills via fallback scan, then the registry file was restored.
