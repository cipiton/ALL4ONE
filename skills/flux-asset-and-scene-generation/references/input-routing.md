# Input Routing

## Accepted Input Shapes

Normalize all of these into one internal bundle before prompt building:

- `02_recap_production/`
- legacy `01_recap_production/`
- a story run folder that contains one of those stage folders
- `04_episode_scene_script.json`
- a `cp-production` output folder such as `outputs/cp-production/<job>/`

## recap-production Mapping

Use:

- `02_assets.json` as the structured asset source
- `04_episode_scene_script.json` as the beat and keyscene-planning source
- `03_image_config.json` as optional style guidance

## cp-production Mapping

Use:

- `03_asset_registry.json` as the structured asset source when present
- `02_beat_sheet.json` as the primary beat-planning source when present
- `04_anchor_prompts.json` as still-image planning support and beat fallback material
- `05_video_prompts.json` only as optional continuity context, not as the primary FLUX still prompt source
- `01_narration_script.txt` only as optional context, never as a direct image prompt

Do not require `cp-production` to mimic recap-production filenames.

## Minimum Viable Inputs

Assets-only can proceed when:

- a structured asset source exists
- or the user is explicitly reviewing previously generated assets without regeneration

Keyscenes can proceed when:

- beat planning exists and usable generated assets exist
- or anchor prompt planning exists and usable generated assets exist

Assets then keyscenes can proceed when:

- a structured asset source exists
- and beat planning or anchor prompt planning exists

## Fallback Rules

- If the user asks for keyscenes only but generated assets are missing, switch to assets then keyscenes when a structured asset source exists.
- If the user asks for keyscenes only and no generated assets or asset source exist, stop clearly.
- If beat planning is missing but anchor prompts exist, derive beat units from anchor prompts.
- If the asset registry is missing, asset generation should stop instead of inventing generic placeholders.
- If only some generated assets exist, reuse the available ones and document the gaps in the manifest.
