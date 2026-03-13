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
  Evidence: `python -m compileall run.py engine skills` passed; `echo 0|python run.py` showed the interactive menu with `recap_analysis` and `recap_production`; smoke runs completed for analysis, production step 1, and production resume into step 2 under root `outputs/`.
