# Implementation Tasks

- [x] Inspect the extracted skill and derive runtime requirements from `SKILL.md`.
  - Evidence: reviewed and normalized root-level `SKILL.md`, plus `references/adaptation-rules.md` and `references/episode-guidelines.md`; runtime enforces `.txt` only and uses the reference markdown files for staged analysis.
- [x] Create the terminal runtime entrypoint and execution pipeline.
  - Evidence: added `run.py` with CLI argument parsing, interactive prompt fallback, input validation, skill discovery, staged pipeline execution, progress logs, and final output path reporting.
- [x] Implement skill loading, planning, routing, staged analysis, formatting, and output writing modules.
  - Evidence: added `engine/skill_loader.py`, `engine/planner.py`, `engine/router.py`, `engine/llm_client.py`, `engine/analyzers.py`, `engine/prompts.py`, `engine/formatter.py`, `engine/writer.py`, and `engine/models.py` for normalized skill parsing, explicit planning, deterministic `.txt` ingestion/chunking, OpenAI-compatible JSON calls, staged analysis, fallback report normalization, and safe file writing.
- [x] Add output handling and repository structure for terminal-only execution.
  - Evidence: created `engine/` package scaffold and `outputs/.gitkeep`; reports are written to `outputs/` with collision-safe filenames such as `<input>_analysis.txt`.
- [x] Verify the runtime behavior with basic checks and document usage and limitations.
  - Evidence: `python -m compileall run.py engine` succeeded; `python run.py sample_novel.txt` progressed through validation, skill loading, plan building, and reference loading, then failed with the expected clear error for a missing `OPENAI_API_KEY`.

- [x] Add local environment-based provider configuration for OpenRouter.
  - Evidence: updated `engine/llm_client.py` to auto-load `.env`, support `LLM_PROVIDER=openrouter`, and pass OpenRouter base URL plus optional attribution headers; added `.env`, `.env.example`, `.gitignore`, and updated `README.md`.

## Completion Summary

Implemented a terminal-only, near-agentic Python runtime that discovers the extracted skill, parses `SKILL.md` as the control plane, plans explicit staged work, reads `.txt` input directly, selectively loads reference markdown files, calls the LLM only for reasoning-heavy stages, normalizes the result, and writes a plain-text report to `outputs/`.

Assumptions and limits:
- The default skill location is the repository root, with fallback discovery by searching for `SKILL.md`.
- The runtime intentionally rejects non-`.txt` input and does not invoke the existing `.docx` extraction path.
- Live analysis requires `OPENAI_API_KEY`; `OPENAI_MODEL` is optional and defaults to `gpt-4.1-mini`.
- Live analysis can now use OpenRouter via `.env` with `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY`.
