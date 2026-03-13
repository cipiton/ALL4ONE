# RECAP123

This repository contains two independent Python tools in the same repo root:

- `recap_analysis/`: skill-driven novel evaluation workflow
- `recap_production/`: interactive drama prep / production helper

Each tool keeps its own code, prompts, references, and outputs inside its folder.

## Run From The Repo Root

Yes, you can run both tools separately from the root with different commands.

Analysis tool:

```bash
python recap_analysis/run.py 
```

Interactive production tool:

```bash
python recap_production/run.py
```

## Windows examples:

```bash
python recap_analysis/run.py 
python recap_production/run.py
```

## Environment Configuration

Both tools use a shared repo-root `.env`.

Recommended setup:

1. Create a `.env` file in the repo root.
2. Put your LLM/API settings there.
3. Run either script from the repo root using the commands above.

## Suggested Repo Layout

```text
RECAP123/
  README.md
  .env
  .env.example
  .gitignore
  recap_analysis/
  recap_production/
```

## Git Notes

The root `.gitignore` excludes:

- `.env` and secret files
- Python cache and virtual environment files
- generated `outputs/` folders

If you want to initialize and push this repo:

```bash
git init
git add .
git commit -m "Initial commit"
```

Then add your remote and push as usual.

## Tool-Specific Docs

See the per-tool docs for workflow details:

- `recap_analysis/README.md`
- `recap_production/README.md`
