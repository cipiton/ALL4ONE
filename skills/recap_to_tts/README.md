# Recap To TTS

This ONE4ALL skill converts one recap-script `.txt` file into episode-level narration WAV files by first running constrained episode-level narrator analysis, then calling the isolated local Qwen TTS runner in `TTS_qwen/`.

## What It Does

1. parses episodes marked by `第 N 集`
2. removes narration labels such as `前置钩子：`, `核心剧情：`, and `结尾悬念：`
3. merges each episode into one narration text block
4. writes a temp text file per episode under `temp\<series_title>\`
5. asks the shared LLM route for one structured narrator analysis per episode:
   - `narrator_gender`
   - `tone`
   - `pace`
   - `energy`
   - `tts_prompt`
6. maps that result to one fixed preset voice only:
   - female: `Vivian` or `Serena`
   - male: `Dylan` or `Uncle_Fu`
7. normalizes the validated analysis into a stable final `prompt_text`
8. reuses exact-text analysis results from `_analysis_cache\` on repeat runs for stability
9. calls `TTS_qwen/tts_runner.py --text-file ... --mode custom_voice --voice ... --prompt_text ...`
10. writes one WAV per episode plus `manifest.json`

## Expected Runner Setup

Set up the isolated TTS workspace first:

```powershell
cd C:\Users\CP\Documents\WORKSPACES\ONE4ALL\TTS_qwen
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Output Layout

Within the normal ONE4ALL skill output run folder, the skill creates:

```text
<run_output>\
  <series_title>\
    <series_title>_ep01.wav
    <series_title>_ep02.wav
    manifest.json
  temp\
    <series_title>\
      <series_title>_ep01.txt
      <series_title>_ep02.txt
```

## v1 Limits

- fixed TTS mode: `custom_voice`
- fixed allowed voice list only: `Vivian`, `Serena`, `Dylan`, `Uncle_Fu`
- one narrator voice per episode only
- no character-level or dialogue-level voice switching yet
- prompt phrasing is normalized locally from the validated analysis result for more stable reruns
- no HTTP service yet; this is local subprocess orchestration only
- stops the whole run on the first failed episode
