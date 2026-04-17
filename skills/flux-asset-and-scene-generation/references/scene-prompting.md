# Scene Prompting

Scene prompts are for FLUX klein keyscenes.

## Core Goal

Write one still-image prompt for one coherent visual moment.

## Reference Roles

When multiple references are present, treat them as role-bearing images:

- image 1 = scene/layout/background
- image 2 = character identity / wardrobe / pose basis
- image 3 = prop / vehicle / design cue

Do not redundantly re-describe everything those images already provide.

Instead, clarify:

- which image dominates the frame
- how the images should combine
- what relationship matters between subject, environment, and prop
- what the shot should feel like visually

## Prompt Focus

Include:

- the main subject and visible state
- the scene and spatial relationship
- the key visual action or frozen dramatic instant
- explicit lighting
- composition or shot framing only when it improves control
- atmosphere when it changes the image

## Keyscene Rules

- Keep it still-image oriented, not video prompting.
- Do not dump recap prose into the prompt.
- Do not write keyword piles.
- Medium-length production prose is preferred.
- Let the reference images carry identity and design detail; use text to control the final relationship and visual emphasis.

## Vehicle / Prop Integration

- Maintain believable size and blocking.
- Keep vehicles grounded in lane, road, workshop, or track space.
- Avoid poster-like oversizing.
