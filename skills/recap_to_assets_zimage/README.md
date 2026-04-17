# Recap To Assets Z-Image

Script-backed ONE4ALL Skill 5 that turns the Skill 4 bridge-stage `assets.json` package into local Z-Image-Turbo renders.

## Files

- spec: `skills/recap_to_assets_zimage/SKILL.md`
- runner: `skills/recap_to_assets_zimage/scripts/generate_assets_zimage.py`
- registry entry: `skills/registry.yaml`

## Input Contract

Preferred input:

```text
outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/assets.json
```

Accepted folder inputs:

```text
outputs/stories/<story_slug>/<run_id>/04_recap_to_comfy_bridge/
outputs/stories/<story_slug>/<run_id>/
```

The skill resolves the selected path to one JSON object with grouped arrays:

- `characters`
- `scenes`
- `props`

Each entry should contain:

- `asset_id` or `name`
- optional `compiled_prompt` from Skill 4 Qwen prompt compilation
- structured prompt fields such as `style_preset`, `style_hint`, `style_lighting`, `core_feature`, `subject_content`, `description`, `prompt_fields`, and `source.raw_lines`
- `prompt` or `prompt_text` only as fallback material

The current bridge skill writes a canonical `assets.json` file that already fits this contract. Do not choose individual generated image files for this stage.

## Output Contract

Outputs land in the story-first run folder:

```text
outputs/stories/<story_slug>/<run_id>/05_assets_t2i/
  characters/
  scenes/
  props/
  manifest.json
```

The stage manifest records:

- story title
- source `assets.json`
- backend path details
- per-asset type, prompt, output file, size, seed, and status

Default render sizes are intentionally small for base asset generation:

- characters: `512x768`
- scenes: `768x512`
- props: `512x512`

## Character Prompt Strategy

Prompt assembly prefers `compiled_prompt` when Skill 4 wrote one. If it is missing, the renderer falls back to structured fields, then to flattened `prompt` / `visual_prompt` text. The structured fallback prefers style fields, core features, subject content, descriptions, character role/traits, `prompt_fields`, and cleaned `source.raw_lines`; flattened prompt text is no longer the main source of truth.

The resolved style is enforced with asset-type-specific prefixes. For 2D runs, the runner adds explicit anime / 动漫风格 mandates:

- characters: high-quality anime style 2D character illustration, 动漫风格, mature animated-drama character design, refined anime linework, detailed painted shading
- scenes: high-quality anime style 2D background illustration, 动漫风格, cinematic anime environment art, layered painted atmosphere, dramatic light and shadow
- props: high-quality anime style 2D prop illustration, 动漫风格, anime production asset design, refined anime linework, detailed painted materials, not product render, not studio product photo

For 3D runs, the runner adds parallel stylized 3D CG prefixes for character, environment, and prop assets. Flattened prompt text cannot override the structured style decision.

When `compiled_prompt` is present, the runner uses it as the primary Z-Image prompt, still applies defensive layout filtering, and adds only missing local style / output guardrails. Old bridge runs without `compiled_prompt` continue to use the existing structured prompt builders.

Character entries keep the same input contract, but the renderer rewrites their generation prompt into a single clean identity reference image:

- one person only
- full body visible, front-facing, neutral standing pose
- plain or unobtrusive background
- no sheet or board-style layout, text overlays, or extra characters

The character prompt builder uses available structured fields such as `core_feature`, `subject_content`, `style_lighting`, `role`, `description`, and `personality_traits` to improve identity separation.

## Scene And Prop Prompt Strategy

Scene prompts are rebuilt as single clean environment references. Props are rebuilt as one clean prop image by default, without reference-sheet layouts. Specialized prop entries are detected from the existing source fields and enriched with single-object product-reference morphology when they look like:

- motorcycles, trail bikes, dirt bikes, off-road bikes, or sport motorcycle prototypes
- motorcycle, motocross, or enduro helmets
- motorcycle engines, especially inline-three / triple-cylinder engines

For these categories, the builder preserves source details such as `subject_content`, `style_lighting`, `description`, and useful cleaned `source.raw_lines`, then adds category-specific morphology and concise negative constraints. Examples include off-road motorcycle features like high front fender, narrow seat, spoke wheels, and knobby tires; motorcycle helmet features like hard shell, chin bar, visor/face opening, and chin strap; and inline-three engine features like a compact straight-row triple-cylinder layout.

Legacy wording that asks for sheet/board layouts is tolerated defensively and stripped during prompt assembly. New recap prompt sources no longer request those layouts by default. Remaining limitation: uncommon mechanical assets still depend on recognizable source terms. If a prop name/description omits the object category or uses highly ambiguous wording, the skill falls back to the generic single-prop strategy rather than guessing a specialized morphology.

2D prop and scene prompts also include anti-realism language to discourage photorealistic, realistic 3D, product-render, and studio-photo drift.

## Backend Assumptions

- local repo: `z-image/`
- local venv: `z-image/.venv/Scripts/python.exe`
- local checkpoint: `z-image/ckpts/Z-Image-Turbo`
- `PYTHONPATH` must include `z-image/src`
- attention backend must be forced to `native`

The skill applies those defaults automatically and lets you override them with:

- `ONE4ALL_ZIMAGE_REPO`
- `ONE4ALL_ZIMAGE_PYTHON`
- `ONE4ALL_ZIMAGE_MODEL`

## Failure Policy

v1 is per-asset tolerant:

- if one asset fails, the stage records the failure in `manifest.json`
- remaining assets still run
- the overall stage still writes a manifest so partial results are inspectable

This is deliberate because asset batches can be long-running and partial output is still useful for debugging or reruns.
