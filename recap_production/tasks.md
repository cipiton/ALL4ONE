# Tasks

- [x] Restructure the project to a root-level runtime with an `engine/` package.
  Evidence: `run.py` is now at the root, support code lives under `engine/`, and the root includes `README.md`, `.gitignore`, `.env.example`, `SKILL.md`, `references/`, `outputs/`, and `tasks.md`.
- [x] Move workflow assets to the root so the app survives removal of `zip` and `extracted`.
  Evidence: `SKILL.md` and `references/step1-prompt.md`, `references/step2-prompt.md`, `references/step3-prompt.md` now exist directly under `recap_production/`.
- [x] Preserve the interactive agent flow with root-based persistence.
  Evidence: root `run.py` still prompts for `.txt` input, style or episode details only when needed, supports resume, avoids auto-chaining, and writes `state.json`, `prompt_dump.json`, and `step_<n>_output.txt` under `outputs/<timestamp>/`.
- [x] Verify the new root layout.
  Evidence: `python -m py_compile run.py engine\\__init__.py engine\\models.py engine\\skill_loader.py engine\\router.py engine\\prompts.py engine\\llm_client.py engine\\writer.py` passed, and `python run.py` from the root completed skill reading, input handling, step detection, prompt loading, and provider-call setup.
- [x] Remove migration leftovers and keep only the essential root project files.
  Evidence: deleted the root zip archive, `extracted/`, `runs/`, root and `engine/` `__pycache__/`, and the smoke-test output directory; the remaining root layout is `run.py`, `SKILL.md`, `references/`, `engine/`, `outputs/.gitkeep`, `README.md`, `.gitignore`, `.env.example`, and `tasks.md`.
- [x] Switch the LLM provider call from OpenAI SDK usage to OpenRouter.
  Evidence: `engine/llm_client.py` now sends a direct `POST` request to OpenRouter's `/chat/completions` endpoint with Bearer auth and optional `HTTP-Referer` and `X-Title` headers, and the smoke run reached the OpenRouter call path before failing only on network reachability in the sandbox.
