# Recap Production Tasks

- [x] Migrate the skill under the shared `skills/` layout.
  Evidence: the skill now lives at `skills/recap_production/` and is discovered by the root runner.
- [x] Convert the skill to standardized frontmatter plus markdown instructions.
  Evidence: `skills/recap_production/SKILL.md` now defines `steps`, `runtime_inputs`, `references`, `execution`, and `output` in frontmatter.
- [x] Preserve resumable step-aware behavior in the shared engine.
  Evidence: the skill uses the shared `step_prompt` strategy, saves `state.json`, and can resume from the latest completed or incomplete step.
- [x] Add a fourth recap-production step for per-episode video scene planning.
  Evidence: `skills/recap_production/SKILL.md` now defines step 4 `输出视频场景脚本`, wired to `references/step4-prompt.md`, with markdown plus JSON outputs.
- [x] Extend accepted step outputs to save a JSON sidecar extracted from reviewed markdown.
  Evidence: `engine/models.py`, `engine/skill_loader.py`, and `engine/executor.py` now support step-level `json_output_filename` / `json_write_to` metadata and persist the parsed fenced JSON block on save.
- [x] Strengthen Step 4 with narration/video alignment precautions and richer beat metadata.
  Evidence: `skills/recap_production/references/step4-prompt.md` now requires `anchor_text`, `priority`, `beat_role`, `pace_weight`, and `asset_focus`, and `skills/recap_production/SKILL.md` now documents the shared-planning and continuity rules for Step 4.
