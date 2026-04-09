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


## Qwen3-TTS Notes

This project currently uses **Qwen3-TTS** through the local `qwen-tts` Python package.

### Model families

Qwen3-TTS provides three main model families:

- **CustomVoice**  
  Best for using built-in preset voices with optional natural-language style control.
- **VoiceDesign**  
  Best for designing a voice from a text description.
- **Base**  
  Best for **voice cloning** from reference audio and for future fine-tuning workflows.

### Current local setup

The current local TTS runner is designed around:

- `custom_voice` mode for preset narration voices
- optional `prompt_text` / `instruct` for style control
- future support for `voice_clone` mode when character voice cloning is needed

### Supported preset CustomVoice speakers

For `Qwen3-TTS-12Hz-1.7B/0.6B-CustomVoice`, the official supported speakers include:

#### Chinese
- `Vivian` — bright, slightly edgy young female voice
- `Serena` — warm, gentle young female voice
- `Uncle_Fu` — seasoned male voice with a low, mellow timbre
- `Dylan` — youthful Beijing male voice with a clear, natural timbre
- `Eric` — lively Chengdu male voice with a slightly husky brightness

#### English
- `Ryan` — dynamic male voice with strong rhythmic drive
- `Aiden` — sunny American male voice with a clear midrange

#### Japanese
- `Ono_Anna` — playful Japanese female voice with a light, nimble timbre

#### Korean
- `Sohee` — warm Korean female voice with rich emotion

> Recommendation: use each speaker’s native language when possible for the best quality.

### How style control works

In `custom_voice` mode, Qwen3-TTS supports an optional natural-language `instruct` prompt.
This can be used to shape:

- emotion
- pacing
- delivery style
- dramatic intensity
- recap / narration tone

Examples of useful narration prompts:

- `用短剧解说旁白的风格，语速中快，节奏紧凑，重点更突出，不要平铺直叙。`
- `中文剧情旁白，语气克制但有戏剧张力，关键反转句更有力，结尾带悬念感。`
- `不要慢，不要像普通念稿。像高能剧情复盘，语速更利落。`
- `像短剧解说博主，语气更抓人，节奏明快，但不要夸张到搞笑。`

### Practical guidance for this project

For Chinese recap narration, good first voices to test are:

- `Dylan`
- `Uncle_Fu`
- `Vivian`

These generally make more sense than English-native voices such as `Ryan` when the narration text is Chinese.

### Future direction for character voice cloning

If future versions of this project need recurring character voices for dramas, cartoons, or series,
the recommended path is to use **Base** models with `voice_clone` mode instead of relying only on preset CustomVoice speakers.

Suggested progression:

1. **v1**: preset CustomVoice narration
2. **v2**: stronger `instruct` / narration-style prompting
3. **v3**: character voice cloning with `Base` model + reference audio
4. **v4**: reusable voice profiles per series / character
