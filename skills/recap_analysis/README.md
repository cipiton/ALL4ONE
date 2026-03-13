# Recap Analysis

Shared-engine skill for evaluating novel `.txt` inputs for recap or audio-drama adaptation.

## Execution Mode

- strategy: `structured_report`
- input: single `.txt` file or non-recursive folder of `.txt` files
- outputs: `outputs/recap_analysis/<timestamp>/...`

## References

- `references/adaptation-rules.md`
- `references/episode-guidelines.md`

## Notes

- The shared engine chunks large inputs automatically before merging a structural summary.
- This skill is not resumable because each run is a single report-generation pass.
