# Qwen TTS Local Workspace

This folder is an isolated Qwen TTS development workspace. It is intentionally separate from the main ONE4ALL app so it can later be used in one of three ways:

- a local subprocess target
- a small local HTTP service
- a cloud-hosted TTS service adapter

For this step, the goal is only local standalone execution from inside `TTS_qwen/`.

## Current Structure

```text
TTS_qwen/
  README.md
  requirements.txt
  tts_runner.py
  .gitignore
  examples/
    example_commands.txt
  logs/
  outputs/
  temp/
```

## Recommended Python Setup

The official Qwen3-TTS project recommends an isolated Python environment and the `qwen-tts` PyPI package. A clean Python 3.12 environment is the safest starting point.

PowerShell steps from `C:\Users\CP\Documents\WORKSPACES\ONE4ALL\TTS_qwen`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional helper tools:

```powershell
pip install "huggingface_hub[cli]"
```

Optional performance dependency for supported NVIDIA setups only:

```powershell
pip install flash-attn --no-build-isolation
```

Do not install this into the main ONE4ALL environment.

## Model Access

`tts_runner.py` accepts either:

- a Hugging Face model ID such as `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- a local model directory path

If you do not pass `--model`, the runner chooses a default model by mode:

- `custom_voice` -> `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- `voice_design` -> `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`
- `voice_clone` -> `Qwen/Qwen3-TTS-12Hz-0.6B-Base`

On first real generation, the Qwen package may download model files automatically. If that fails, supply a local downloaded model path with `--model`.

## Runner Interface

`tts_runner.py` is a standalone CLI entry point designed to stay stable even if the underlying Qwen adapter code needs later updates.

Supported arguments:

- `--text`: inline text to synthesize
- `--text-file`: UTF-8 text file to synthesize instead of inline text
- `--output`: output audio path
- `--mode`: `custom_voice`, `voice_design`, or `voice_clone`
- `--ref_audio`: required for `voice_clone`
- `--voice`: required for `custom_voice`
- `--prompt_text`: mode-specific prompt text

`--text` and `--text-file` are mutually exclusive. You must provide exactly one of them.

How `--prompt_text` is used:

- `custom_voice`: optional speaking style / instruction
- `voice_design`: required natural-language voice description
- `voice_clone`: optional transcript for the reference audio

If `voice_clone` is used without `--prompt_text`, the runner falls back to embedding-only clone mode. That is convenient for testing, but quality may be lower than transcript-guided cloning.

## Smoke Test

CLI-only smoke test, no model load:

```powershell
python .\tts_runner.py --text "Hello from Qwen TTS." --output .\outputs\smoke_test.wav --mode custom_voice --voice Ryan --dry-run
```

Long-text smoke test via file:

```powershell
python .\tts_runner.py --text-file .\examples\episode_sample.txt --output .\outputs\smoke_test.wav --mode custom_voice --voice Ryan --dry-run
```

First real synthesis test:

```powershell
python .\tts_runner.py --text "Hello from Qwen TTS." --output .\outputs\smoke_test.wav --mode custom_voice --voice Ryan
```

## Notes

- The script creates the output directory automatically.
- For longer narration, prefer `--text-file` over very large inline `--text` shell arguments.
- Error handling is included for missing dependencies, invalid paths, missing model access, and unsupported argument combinations.
- The Qwen invocation code is intentionally isolated in an adapter section so a future FastAPI or subprocess wrapper can reuse the same request model.

## References

- Official repo: <https://github.com/QwenLM/Qwen3-TTS>
- Official package metadata: <https://raw.githubusercontent.com/QwenLM/Qwen3-TTS/main/pyproject.toml>
