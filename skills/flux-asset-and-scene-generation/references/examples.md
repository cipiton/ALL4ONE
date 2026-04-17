# Examples

## Example 1: recap-production -> assets only

Input:

- `02_recap_production/`
- contains `02_assets.json`
- user intent: `assets only`

Decision:

- run `asset`
- generate `characters`, `props`, and `scenes`
- do not enter keyscene mode

Why:

- structured asset planning exists
- the user only wants reusable reference images

## Example 2: cp-production -> keyscenes requested but no assets exist

Input:

- `outputs/cp-production/<job>/`
- contains `02_beat_sheet.json`, `03_asset_registry.json`, `04_anchor_prompts.json`
- no reusable generated assets found
- user intent: `keyscenes`

Decision:

- upgrade to `asset_then_keyscene`

Why:

- keyscene continuity needs real generated still-image references
- the asset registry exists, so the skill can generate them first

## Example 3: cp-production -> keyscenes with reusable assets already present

Input:

- `outputs/cp-production/<job>/`
- contains `02_beat_sheet.json`, `05_video_prompts.json`, `04_anchor_prompts.json`
- reusable generated assets already found in `generated_assets/`
- user intent: `continue to scenes`

Decision:

- run `keyscene`
- reuse the existing assets
- do not regenerate assets unless a required group is missing

Why:

- the continuity anchors already exist
- the beat planning is sufficient for still-image scene construction

## Example 4: incomplete cp-production bundle

Input:

- `outputs/cp-production/<job>/`
- contains only `04_anchor_prompts.json`
- no asset registry
- no generated assets

Decision:

- stop clearly

Why:

- anchor planning alone is not enough to fabricate missing asset continuity
- the honest fallback is to name the missing asset source and generated asset folders
