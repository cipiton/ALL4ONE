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
      en: "Stage 03 TTS. Preferred input is the Skill 2 `02_recap_production` folder; the runtime resolves `01_recap_script.txt` before running narrator analysis and the isolated Qwen TTS runner."
      zh: "第 03 阶段配音。首选输入为第 2 个技能产出的 `02_recap_production` 文件夹；运行时会解析其中的 `01_recap_script.txt`，再执行旁白分析并调用隔离的 Qwen TTS 运行器。"
    input_hint:
      en: "Skill 3 input: send the Skill 2 `02_recap_production/` folder. Fallback: `02_recap_production/01_recap_script.txt`."
      zh: "第 3 个技能输入：请提供第 2 个技能产出的 `02_recap_production/` 文件夹。回退输入：`02_recap_production/01_recap_script.txt`。"
    output_hint:
      en: "Writes one WAV per episode plus `manifest.json` under the story-first `03_recap_to_tts` stage folder."
      zh: "会在故事优先输出结构的 `03_recap_to_tts` 阶段目录下写出每集一个 WAV，以及一个 `manifest.json`。"
    starter_prompt:
      en: "Send the `02_recap_production` folder from Skill 2, or its `01_recap_script.txt` file."
      zh: "请提供第 2 个技能产出的 `02_recap_production` 文件夹，或其中的 `01_recap_script.txt` 文件。"

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

Convert a Skill 2 recap-production bundle into episode-level narration audio by combining constrained episode analysis with the isolated `TTS_qwen/tts_runner.py` runner.

## Expected Input Format

Preferred input:

- `outputs/stories/<story_slug>/<run_id>/02_recap_production/`

Fallback input:

- `outputs/stories/<story_slug>/<run_id>/02_recap_production/01_recap_script.txt`

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

- `outputs/stories/<story_slug>/<run_id>/03_recap_to_tts/<story_title>_ep01.wav`
- `outputs/stories/<story_slug>/<run_id>/03_recap_to_tts/<story_title>_ep02.wav`
- `outputs/stories/<story_slug>/<run_id>/03_recap_to_tts/manifest.json`

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
