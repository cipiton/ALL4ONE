# Recap To Keyscene Kontext

Script-backed ONE4ALL Skill 6 that creates stage-06 recap keyscene I2I images through a running ComfyUI Flux Kontext API workflow.

## Files

- spec: `skills/recap_to_keyscene_kontext/SKILL.md`
- runner: `skills/recap_to_keyscene_kontext/scripts/run_keyscene_kontext.py`
- workflow template: `skills/recap_to_keyscene_kontext/assets/i2iscenes.json`
- registry entry: `skills/registry.yaml`

## Input Contract

Preferred input:

```text
outputs/stories/<story_slug>/<run_id>/
```

The story run folder should already contain Skill 4 bridge outputs and Skill 5 T2I assets.

Accepted single-path fallbacks:

```text
outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/
outputs/stories/<story_slug>/<run_id>/05_assets_t2i/
outputs/stories/<story_slug>/<run_id>/05_assets_t2i/characters/
<any file inside 04_recap_to_comfy_bridge/>
<any file inside 05_assets_t2i/ or 05_assets_t2i/characters|scenes|props/>
```

The runner resolves both required stages automatically:

- `04_recap_to_comfy_bridge/videoarc_storyboard.json`
- `05_assets_t2i/characters/`
- `05_assets_t2i/scenes/`
- `05_assets_t2i/props/`

Legacy `03_recap_to_comfy_bridge/` and `04_assets_t2i/` folders are still accepted for existing runs.

No manual per-image selection is needed.

## Output Contract

Outputs land in the story-first run folder:

```text
outputs/stories/<story_slug>/<run_id>/06_keyscene_i2i/
  ep01_s01.png
  ep01_s02.png
  manifest.json
  payloads/
    ep01_s01.json
    ep01_s02.json
```

In dry-run mode, the skill writes payload JSON and the manifest but does not write image files.

## Matching

For each beat, the runner prefers explicit `asset_hints` from `videoarc_storyboard.json`:

- `asset_hints.scenes`
- `asset_hints.characters`
- `asset_hints.props`

It scores exact matches first, then substring matches, then beat-text substring matches, then token overlap. If no match is found, it uses the first available asset in that group and records a fallback note in `manifest.json`. v1 chooses one primary scene, up to one primary character, and up to one primary prop per beat. Extra hints are recorded as a v1 limitation note.

## Workflow Substitution

The bundled template is ComfyUI API JSON, not a Python image-generation pipeline. The runner mutates a copy per beat:

- identifies `LoadImage` nodes by `_meta.title` terms such as character, scene, and prop, with node-order fallback
- injects ComfyUI upload filenames, or local paths when upload is disabled / dry-run
- rewires the two `ImageStitch` nodes and the final `FluxKontextImageScale` input to respect the selected reference order
- replaces the first non-negative text-encode node's `text`
- replaces `SaveImage.filename_prefix`
- replaces numeric `width`, `height`, and `seed` fields where present

The model-loader nodes stay unchanged by default, including the Flux Kontext FP8 UNET entry.

Current bundled template chain:

- `190` character `LoadImage`
- `191` scene `LoadImage`
- `194` prop `LoadImage`
- `146` first `ImageStitch`
- `42` scale-after-stitch-1
- `192` second `ImageStitch`
- `195` final `FluxKontextImageScale`
- `124` `VAEEncode`
- `177` `ReferenceLatent`

Before this update the effective fixed order was:

- stitch 1 = `character + prop`
- stitch 2 = `(character + prop) + scene`

Default output is mobile-first and portrait-first. The v1 baseline is `576x1024` to keep keyscene generation lighter. Use `768x1344` when a higher-quality portrait pass is worth the extra runtime. Landscape or other sizes can still be requested with explicit width/height overrides, but landscape is not the default.

## Prompt Cleanup

The keyscene runner can optionally use the configured Gemini alias as a prompt director / prompt normalizer before the final prompt goes into ComfyUI.

Flow:

1. collect compact beat fields already used by the runner
2. send a structured, low-noise JSON request to Gemini
3. validate and sanitize the JSON response
4. assemble a concise final prompt from fixed ordered fields
5. continue through the existing image pipeline unchanged

Structured cleanup schema:

- `shot_intent`
- `framing`
- `performance`
- `scene`
- `essential_prop`
- `style_tail`
- `shot_priority`
- `negative_guidance`

What it is for:

- reduce the long manifest-style prompt into a shorter visual prompt
- keep the beat literal and cinematic
- optionally provide `shot_priority` to the existing reference-order policy

What it is not:

- it is not the image model
- it should not invent story facts
- it should not add new people, props, or locations
- it should not output poetic prose or keyword soup

Modes and overrides:

- default: `gemini`
- optional override: `off`
- env: `ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODE=off|gemini`
- env: `ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODEL=gemini`
- CLI: `--prompt-cleanup-mode off|gemini`
- CLI: `--prompt-cleanup-model gemini`

Fallback behavior:

- invalid JSON
- missing required fields
- malformed / verbose response
- config or provider failure

In all of those cases, the runner logs a warning and falls back to the legacy prompt builder automatically.

Debugging:

- env: `ONE4ALL_KONTEXT_DEBUG_PROMPT_CLEANUP=1`
- CLI: `--debug-prompt-cleanup`

When debug is enabled, the runner writes `prompt_cleanup_debug/<beat_id>.json` containing:

- structured input sent to Gemini
- raw response text / raw provider JSON
- validated structured payload
- final assembled prompt
- legacy prompt

## Reference Ordering

Supported modes:

- `identity_first`: `character -> scene -> prop`
- `staging_first`: `scene -> character -> prop`
- `object_first`: `prop -> scene -> character`

Auto mode is the default and is shot-aware:

- close-up / medium close-up / emotion / dialogue beats -> `identity_first`
- wide / establishing / staging-heavy / interaction beats -> `staging_first`
- insert / object-centric / prop-reveal beats -> `object_first`

Fallback behavior:

- 1 usable reference -> inject that single reference directly into the final scale node
- 2 usable references -> stitch only the first two according to the selected mode
- 3 usable references -> stitch the first pair, then add the third reference in stitch 2

Manual overrides:

- env: `ONE4ALL_KONTEXT_REFERENCE_ORDER_MODE=identity_first|staging_first|object_first`
- CLI: `--reference-order-mode identity_first|staging_first|object_first`
- per beat: `reference_order_mode` or `asset_hints.reference_order_mode`

Debug / inspection:

- CLI: `--debug-reference-order`
- env: `ONE4ALL_KONTEXT_DEBUG_REFERENCE_ORDER=1`

Per-beat `manifest.json` entries now record:

- selected `shot_priority`
- final `reference_order.mode`
- chosen references in order
- target stitch / scale node mapping under `workflow_substitutions.reference_injection`

## Backend Assumptions

- ComfyUI is already running for live runs
- live execution is the default behavior
- endpoint resolution order: `ONE4ALL_COMFYUI_URL`, then `http://127.0.0.1:8188`
- prompt cleanup model alias defaults to `model_aliases.gemini` from `config.ini`
- override template with `ONE4ALL_KONTEXT_WORKFLOW_TEMPLATE`
- override reference order with `ONE4ALL_KONTEXT_REFERENCE_ORDER_MODE`
- dry validate with CLI `--dry-run` or `ONE4ALL_KONTEXT_DRY_RUN=1`
- limit validation work with `ONE4ALL_KONTEXT_LIMIT=1`
- default size: `576x1024`
- higher portrait option: `768x1344`

The skill no longer needs a normal-use endpoint or dry-run prompt. Those are advanced overrides now; the default path is "send the story run folder and run live against the configured local ComfyUI endpoint."

## Validation

Before any ComfyUI submission, the runner validates:

- `04_recap_to_comfy_bridge/videoarc_storyboard.json`
- `05_assets_t2i/characters/`
- `05_assets_t2i/scenes/`
- `05_assets_t2i/props/`
- the selected scene, character, and prop image path for each beat

If a required path is missing, the run fails clearly instead of building a broken payload. Beat-level preflight failures are written into `06_keyscene_i2i/manifest.json` with additive `error_stage` and `missing_paths` fields.

Manual dry-run example:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152 --dry-run --limit 1
```

Manual live example:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152 --limit 1
```

Convenience fallback example using the bridge folder:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152\04_recap_to_comfy_bridge --dry-run --limit 1
```

Convenience fallback example using the assets folder:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152\05_assets_t2i --dry-run --limit 1
```

Manual reference-order override example:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152 --dry-run --limit 1 --reference-order-mode staging_first --debug-reference-order
```

Gemini prompt-cleanup example:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152 --dry-run --limit 1 --prompt-cleanup-mode gemini --debug-prompt-cleanup
```

Minimal local validation script:

```powershell
python skills\recap_to_keyscene_kontext\scripts\validate_reference_order.py
python skills\recap_to_keyscene_kontext\scripts\validate_prompt_cleanup.py
```

Higher-quality portrait example:

```powershell
python skills\recap_to_keyscene_kontext\scripts\run_keyscene_kontext.py outputs\stories\zxmoto\20260413_131152 --limit 1 --width 768 --height 1344
```

## v1 Limitations

- one output image per beat
- one primary scene, one primary character, and one primary prop per beat
- no multi-character or multi-prop compositing beyond choosing the strongest primary match
- no automatic ComfyUI startup
- the bundled workflow is the provided v1 exported ComfyUI API workflow; if the graph changes in ComfyUI, replace `assets/i2iscenes.json` with a fresh API export
