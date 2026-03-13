# Recap Production

Shared-engine skill for multi-step recap production and asset preparation.

## Execution Mode

- strategy: `step_prompt`
- input: single `.txt` file or non-recursive folder of `.txt` files
- outputs: `outputs/recap_production/<timestamp>/...`
- resume: enabled

## Runtime Inputs

- `episode_count` on step 1 when the input is not a rewrite task
- `style` on step 2

## References

- `references/step1-prompt.md`
- `references/step2-prompt.md`
- `references/step3-prompt.md`
