# Drama Prep Helper

Run the interactive helper from the workspace root:

```bash
python recap_production/run.py
```

The runner uses `SKILL.md` as the workflow source of truth, loads only the selected step prompt from `references/`, and stores each run under `outputs/<timestamp>/`.

The runtime reads its configuration from the repo-root `.env`.
