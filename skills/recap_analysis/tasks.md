# Recap Analysis Tasks

- [x] Migrate the skill under the shared `skills/` layout.
  Evidence: the skill now lives at `skills/recap_analysis/` and is discovered by the root runner.
- [x] Convert the skill to standardized frontmatter plus markdown instructions.
  Evidence: `skills/recap_analysis/SKILL.md` now defines `steps`, `references`, `execution.stages`, and `output` in frontmatter.
- [x] Preserve the structured evaluation behavior in the shared engine.
  Evidence: the skill uses the shared `structured_report` strategy with staged JSON outputs and a final rendered report.
