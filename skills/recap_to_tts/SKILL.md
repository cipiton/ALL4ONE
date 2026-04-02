---
name: recap_to_tts
display_name: Recap To TTS
description: Convert a recap script `.txt` into episode-level narration WAV files by calling the isolated local Qwen TTS runner.
supports_resume: false
input_extensions:
  - .txt
folder_mode: non_recursive
metadata:
  i18n:
    display_name:
      en: "Recap To TTS"
      zh: "解说稿转配音"
    description:
      en: "Split a recap script into episode narration clips and generate one WAV per episode with local Qwen TTS."
      zh: "将解说剧脚本拆成分集旁白，并用本地 Qwen TTS 生成每集一个 WAV。"
    workflow_hint:
      en: "This workflow is deterministic and local. It parses the recap script, then shells out to the isolated Qwen TTS runner for each episode."
      zh: "此流程是本地确定性脚本流程：先解析解说稿，再逐集调用隔离的 Qwen TTS 运行器。"
    input_hint:
      en: "Send one recap-script `.txt` file that uses episode markers like `第 1 集` and sections like `前置钩子` / `核心剧情` / `结尾悬念`."
      zh: "请提供一个解说稿 `.txt` 文件，格式需包含 `第 1 集` 这类分集标记，以及 `前置钩子` / `核心剧情` / `结尾悬念` 这类分段标签。"
    output_hint:
      en: "Writes one WAV per episode plus `manifest.json` under the current project output folder."
      zh: "会在当前项目输出目录下写出每集一个 WAV，以及一个 `manifest.json`。"
    starter_prompt:
      en: "Send the recap script `.txt` file you want to convert into narration audio."
      zh: "请提供要转成旁白音频的解说稿 `.txt` 文件。"

steps:
  - number: 1
    title: Generate Episode Narration Audio
    description: Parse the recap script into episodes and call the local Qwen TTS runner once per episode.
    write_to: manifest
    default: true

execution:
  strategy: utility_script
  utility_script:
    path: scripts/generate_recap_tts.py
    entrypoint: run

output:
  mode: text
  filename_template: manifest.json
  include_prompt_dump: false
---

# Recap To TTS

Convert a recap script `.txt` into episode-level narration audio by reusing the isolated `TTS_qwen/tts_runner.py` runner.

## Expected Input Format

The source file should contain episode markers like:

- `第 1 集`
- `第 2 集`
- `第 3 集`

Inside each episode, the parser strips these labels from spoken narration while keeping their content:

- `前置钩子：`
- `核心剧情：`
- `结尾悬念：`

## Output

For an input file such as `01_recap_script.txt`, the skill writes:

- `outputs/recap_to_tts/<run>__/01_recap_script/01_recap_script_ep01.wav`
- `outputs/recap_to_tts/<run>__/01_recap_script/01_recap_script_ep02.wav`
- `outputs/recap_to_tts/<run>__/01_recap_script/manifest.json`

`manifest.json` records the source file, episode numbers, output filenames, durations as `mm:ss`, and per-episode success status.

## Runtime Notes

- v1 uses fixed TTS settings: `--mode custom_voice --voice Ryan`
- the skill stops on the first failed episode
- the skill expects the isolated TTS environment to exist under `TTS_qwen/.venv/`
- you can override the Python or runner path with environment variables:
  - `ONE4ALL_QWEN_TTS_PYTHON`
  - `ONE4ALL_QWEN_TTS_RUNNER`
