# Recap Production Tasks

- [x] Migrate the skill under the shared `skills/` layout.
  Evidence: the skill now lives at `skills/recap_production/` and is discovered by the root runner.
- [x] Convert the skill to standardized frontmatter plus markdown instructions.
  Evidence: `skills/recap_production/SKILL.md` now defines `steps`, `runtime_inputs`, `references`, `execution`, and `output` in frontmatter.
- [x] Preserve resumable step-aware behavior in the shared engine.
  Evidence: the skill uses the shared `step_prompt` strategy, saves `state.json`, and can resume from the latest completed or incomplete step.
