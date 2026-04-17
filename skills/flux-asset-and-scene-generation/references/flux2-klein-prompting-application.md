# FLUX.2 klein Prompting Application

Source guide:

- https://docs.bfl.ai/guides/prompting_guide_flux2_klein

This skill applies the official FLUX.2 klein guide in two different prompt patterns.

## Asset Prompt Pattern

Use richer prose prompts for characters, props, and scenes.

Order:

1. Main subject first
2. Setting or framing
3. Specific visual details
4. Lighting
5. Atmosphere
6. Explicit style tail

Skill implementation:

- character prompts start with identity-defining visual traits, then place the character in a clean reference-style frame
- scene prompts start with the environment itself, then expand into space, detail, and lighting
- prop prompts start with the object itself, then clarify structure, materials, and visible wear

Why:

- the guide says klein works best with scene-first prose, not keyword bags
- the guide says lighting has the biggest impact on output quality
- the guide says important elements should be front-loaded

## Keyscene Prompt Pattern

Use shorter multi-reference integration prompts.

Order:

1. State the core beat first
2. State the target relation or target state
3. Add one still-image framing clause
4. End with one compact style clause

Skill implementation:

- reference images carry most appearance and scene detail
- the prompt does not say `图1/图2/图3` in final text
- the prompt focuses on what should be established in the edited still image, not on re-describing every reference
- the skill classifies each beat into:
  - `staging_keyscene`
  - `identity_emotion_keyscene`
  - `insert_object_keyscene`
  - `vehicle_keyscene`
- staging prompts emphasize scene relation and subject placement
- identity/emotion prompts emphasize face, expression, posture, and one supporting environment cue
- insert/object prompts emphasize the object, local interaction, and local lighting
- vehicle prompts emphasize physical scale, blocking, road / track readability, and visible surrounding space
- the prompt stays in a medium-length production range so the references remain dominant

## Vehicle Shot Pattern

Use a dedicated vehicle-shot template when the beat is dominated by a motorcycle, bike, car, engine build, or track action.

Order:

1. Core action
2. Physical scale and rider / object relation
3. Blocking and scene relation
4. One framing clause
5. One compact style clause

Skill implementation:

- road and standing vehicle beats default to `scene + character`
- track or object-dominant vehicle beats can use `scene + prop`
- `scene + character + prop` is reserved for exact-design beats where the vehicle identity is genuinely critical
- if a vehicle prop would likely cause oversized poster-like staging, the skill drops that prop reference and keeps the vehicle identity in prompt text instead
- anti-oversize rules stay concise: real-world proportions, natural camera distance, lane / track fit, visible environment space

Why:

- the guide says references should carry visual detail, so the prompt should focus on the target physical relationship
- still-image editing works better when the prompt anchors scale and placement instead of retelling narrative mood
- FLUX.2 klein responds better to concise prose about the desired final frame than to long cinematic narration

## Style Handling

The skill supports:

- `realism`
- `3d-anime`
- `2d-anime-cartoon`

Application rule:

- keep style explicit at the end of the prompt
- do not bury style in the middle of unrelated detail
- keep the style phrasing consistent across all images in the same run

Default style derivation:

- recap `2D` -> `2d-anime-cartoon`
- recap `3D` -> `3d-anime`
- recap realistic / 写实 -> `realism`

## What To Avoid

Avoid these failure modes from the guide:

- keyword soup
- vague requests such as “make it better”
- overstuffed prompts that restate every visible trait even when references already provide them
- burying the main subject deep in the prompt
- weak lighting language

Avoid these workflow-specific mistakes:

- turning asset prompts into multi-angle boards or character sheets
- turning keyscene prompts into a second full asset prompt instead of an edit/integration prompt
- using motion-control language like `pan`, `push in`, `dolly out`, or `handheld drift` as if the model were generating a video clip
- forcing 3 references when `scene + character` or `scene + prop` is enough
- letting vehicle props force giant foreground motorcycles when `scene + character` would keep scale more stable
- describing vehicles like poster objects instead of integrating them into lane, road, track, or workshop space
- using Comfy Bridge as the primary input source for this skill
