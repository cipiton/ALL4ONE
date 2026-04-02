# Recap To TTS

This ONE4ALL skill converts one recap-script `.txt` file into episode-level narration WAV files by calling the isolated local Qwen TTS runner in `TTS_qwen/`.

## What It Does

1. parses episodes marked by `第 N 集`
2. removes narration labels such as `前置钩子：`, `核心剧情：`, and `结尾悬念：`
3. merges each episode into one narration text block
4. writes a temp text file per episode under `temp\<series_title>\`
5. calls `TTS_qwen/tts_runner.py --text-file ... --mode custom_voice --voice Ryan`
6. writes one WAV per episode plus `manifest.json`

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
- fixed voice: `Ryan`
- no HTTP service yet; this is local subprocess orchestration only
- stops the whole run on the first failed episode
