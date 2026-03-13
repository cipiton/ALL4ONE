# Novel Evaluation Runtime

Terminal-only Python runtime for skill-driven novel evaluation using `.txt` input.

## Requirements

- Python 3.10+
- Configure your API settings in `.env`
- Default provider flow is OpenRouter

## Project Layout

- `run.py`: CLI entrypoint
- `SKILL.md`: skill control plane
- `references/`: reference markdown files loaded selectively during analysis
- `engine/`: runtime modules
- `outputs/`: generated `.txt` reports

## Run A Test

First, edit `.env` in the repo root and set:

```text
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_real_openrouter_key
OPENROUTER_MODEL=openai/gpt-4.1-mini
```

Optional OpenRouter settings:

```text
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=
OPENROUTER_APP_TITLE=Novel Evaluation Runtime
```

From the repo root:

```bash
python recap_analysis/run.py path/to/your_novel.txt
```

Windows example:

```bash
python recap_analysis/run.py C:\path\to\your_novel.txt
```

If you omit the path, the script will prompt for it:

```bash
python recap_analysis/run.py
```

After each completed analysis or handled error, the script returns to the file prompt instead of exiting automatically. Press Enter on a blank prompt, or type `q`, `quit`, or `exit`, to stop.

## Expected Behavior

The runtime will:

1. Validate that the input exists and ends with `.txt`
2. Load `SKILL.md`
3. Build an execution plan
4. Load only the relevant files from `references/`
5. Run staged LLM analysis
6. Write the final report to `outputs/`

Output filename pattern:

```text
<input_name>_analysis.txt
```

If that file already exists, a timestamp is added automatically.

## Common Errors

- Missing file: the provided path does not exist
- Non-txt file: only `.txt` input is supported
- Empty file: the input file has no usable text
- Missing API key: `OPENROUTER_API_KEY` is not set while `LLM_PROVIDER=openrouter`
- Wrong provider config: `.env` points at a provider without the required key/model values
