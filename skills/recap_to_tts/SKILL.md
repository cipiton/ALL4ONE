---
name: recap_to_tts
display_name: Recap To TTS
description: Convert a recap script `.txt` into episode-level narration WAV files with constrained LLM-guided narrator analysis plus the isolated local Qwen TTS runner.
supports_resume: false
input_extensions:
  - .txt
folder_mode: non_recursive
model_routing:
  step_execution_model: fast
metadata:
  i18n:
    display_name:
      en: "Recap To TTS"
      zh: "解说稿转配音"
    description:
      en: "Split a recap script into episode narration clips, infer one narrator style per episode, and generate one WAV per episode with local Qwen TTS."
      zh: "将解说剧脚本拆成分集旁白，先为每集推断单一旁白风格，再用本地 Qwen TTS 生成每集一个 WAV。"
    workflow_hint:
      en: "This workflow keeps local deterministic orchestration: it parses the recap script, runs constrained episode-level narrator analysis, then shells out to the isolated Qwen TTS runner for each episode."
      zh: "此流程保持本地确定性编排：先解析解说稿，再做受约束的分集旁白分析，最后逐集调用隔离的 Qwen TTS 运行器。"
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

Convert a recap script `.txt` into episode-level narration audio by combining constrained episode analysis with the isolated `TTS_qwen/tts_runner.py` runner.

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

`manifest.json` records the source file, episode numbers, output filenames, durations as `mm:ss`, per-episode success status, and narrator-analysis debug fields such as the selected preset voice and `prompt_text`.

## Runtime Notes

- v1 always calls Qwen with `--mode custom_voice`
- before each TTS call, the skill asks the shared LLM route for a constrained JSON result:
  - `narrator_gender`: `female` or `male`
  - `tone`: one of `revengeful`, `cold`, `suspenseful`, `tragic`, `bitter`, `triumphant`, `high_energy_recap`, `reflective`
  - `pace`: one of `slow`, `medium`, `medium_fast`, `fast`
  - `energy`: one of `low`, `medium`, `high`
  - `tts_prompt`: short Chinese delivery guidance for Qwen
- the script then normalizes that structured result into a stable final `prompt_text` before calling Qwen, so repeated runs do not depend on freeform prompt phrasing
- the model is not allowed to invent speaker names; the script maps only to fixed preset voices:
  - female: `Vivian`, `Serena`
  - male: `Dylan`, `Uncle_Fu`
- v1 keeps one narrator voice per episode and does not do character-level voice switching
- exact episode-text analysis results are memoized under the skill output root `_analysis_cache/` to improve repeat-run stability
- if the LLM result is missing or invalid, the script falls back safely to the default female narrator path with the built-in default `prompt_text`
- the skill stops on the first failed episode
- the skill expects the isolated TTS environment to exist under `TTS_qwen/.venv/`
- you can override the Python or runner path with environment variables:
  - `ONE4ALL_QWEN_TTS_PYTHON`
  - `ONE4ALL_QWEN_TTS_RUNNER`
