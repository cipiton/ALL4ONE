# Output Contract

## Generated Folders

Asset runs write:

- `generated_assets/characters/*.png`
- `generated_assets/props/*.png`
- `generated_assets/scenes/*.png`
- `generated_assets/**/*.resolved_prompt.txt`
- `generated_assets/manifest.json`

Keyscene runs write:

- `generated_keyscenes/keyscenes/*.png`
- `generated_keyscenes/keyscenes/*.resolved_prompt.txt`
- `generated_keyscenes/manifest.json`

Combined runs write:

- `generated_assets/`
- `generated_keyscenes/`
- `generated_keyscenes/combined_manifest.json`

## Manifest Requirements

Each manifest should include:

- source folder
- normalized input contract
- source file paths actually used
- workflow plan decision
- selected style target
- final prompt language
- prompt authorship metadata
- chosen model/backend
- generated item list

Keyscene items should also include:

- selected reference assets
- reference policy
- shot mode
- fallback notes
- validation warnings
- resume status when applicable

## Debug Requirements

When keyscene debug mode is enabled, save one JSON per beat that records:

- chosen references
- shot mode
- template choice
- final prompt language
- source structured input
- final rendered prompt
- fallback decisions
- scene-validation notes

## Compatibility Rule

The emitted outputs must remain usable by the current ONE4ALL runtime and by downstream local review workflows. Do not invent a separate output layout for cp-production inputs.
