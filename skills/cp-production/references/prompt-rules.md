# Prompt Rules

## Core Principle

Narration explains the story. Prompts instruct models. They are not interchangeable.

The skill exists to prevent this failure mode:
- raw prose becomes recap text
- recap text gets reused as both image prompt and video prompt
- both models receive bloated, mixed-purpose instructions

Instead, convert story prose into:
- narration script
- beats
- assets
- anchor prompts
- video prompts

## Why Narration Script Is Not a Prompt

- Narration needs spoken clarity, pacing, and emotional readability.
- Prompts need concrete, controllable visual or motion instructions.
- Narration can mention causality, context, and backstory.
- Prompts should mostly describe what is visible and actionable for the model.

## Anchor Prompts for FLUX.2 klein

Anchor prompts are still-image instructions.

Prioritize:
- visible subject
- environment
- main object
- shot size
- composition
- lighting
- visible state
- stable style
- dramatic focus
- continuity cues from adjacent beats

Anchor prompt style:
- literal
- composition-oriented
- single-frame
- controllable
- cinematic scene-planning language
- strong enough to work as a storyboard keyframe

Avoid:
- symbolic prose
- theme statements
- long emotional explanation
- dialogue unless visually necessary
- montage language
- multi-stage action in one still
- poetic wording that weakens control
- metadata-list phrasing
- field-by-field prompt assembly
- visually correct but emotionally flat prompts
- composition terms with no real scene tension
- continuity loss between adjacent beats

Short rule:
- anchor prompts = visible composition + dramatic still-frame intent

## Scene Dramatization Layer

Before writing anchor or video prompts, use each beat as a scene design object, not as a direct prompt source.

For every beat, internally resolve:
- `visual_core`: the strongest visible idea of the beat.
- `dramatic_focus`: the pressure or reveal the shot must carry.
- `continuity_notes`: what stays stable from the previous beat or changes for a clear reason.
- `subject_priority`, `environment_priority`, and `prop_priority`: what the viewer must notice first, second, and only as support.
- `strongest_single_frame_interpretation`: the one most compelling still frame.
- `strongest_motion_interpretation`: the best continuation after the anchor frame.
- `shot_design`: composition, light, foreground/background, spacing, and visual hierarchy.
- `camera_intent`: why the camera is static, pushing, tracking, revealing, or pulling away.
- `emotional_pressure`: the visible action pressure, not abstract feeling.
- `stability_notes`: identity, wardrobe, scale, prop state, style, and location constraints.

Do not output this as a separate artifact unless the step schema asks for the fields. Use it to render stronger separated outputs.

## Asset-Type Continuity

Cinematic dramatization must never change production facts.

- Preserve exact asset categories from the beat sheet and asset registry.
- A motorcycle, bike, or racing motorcycle must never become a car.
- A motorcycle frame must never become a car chassis.
- For `ZXMOTO 820RR-RS`, always use racing motorcycle, sportbike, motorcycle, bike, fairing, bodywork, front wheel, rear wheel, rider, lean angle, braking, apex. Never use car, race car, automobile, driver cockpit, or car chassis.
- Vehicle scale, wheel count, rider relationship, direction of travel, livery, and model identity must remain stable.
- Props must remain the same kind of prop unless the story explicitly changes them.
- If stronger wording is needed, intensify composition, light, pressure, motion, and camera intent instead of changing what the asset is.

## Video Prompts for LTX-2

Video prompts assume the anchor frame already covers:
- subject
- scene
- style

So the LTX-2 prompt should emphasize:
- visible motion
- environmental motion
- character action
- camera movement
- pacing or intensity when useful

Video prompt style:
- shorter than the anchor prompt
- motion-first
- clear about the next action
- camera-aware
- anchored to the existing still frame
- continuity-aware

Avoid:
- re-describing the whole frame
- recap-style summary language
- abstract emotional interpretation without visible cues
- overloaded multi-event action that should have been split into multiple beats
- starting a new scene from scratch
- ignoring identity, wardrobe, prop, vehicle-scale, or location continuity

Short rule:
- video prompts = anchor continuation + motion + camera

## Style Rendering Rules

If the runtime, user, or asset registry provides `visual_style` or `style`, preserve it. Do not require a new user input.

- `realism`: realistic cinematic image prompting, credible materials, natural camera/lens feel.
- `2D`: illustrated / anime / drawn-image style prompting, linework and painted shading.
- `3D`: default to `anime_donghua_3d` unless an explicit `3d_style_variant` overrides it.

When `visual_style = 3D`, inject a premium stylized East Asian CG direction:
- anime-inspired 3D character design
- donghua-style facial structure
- sharper silhouettes
- clean line-of-action
- elegant proportions
- dramatic cinematic lighting
- refined material rendering
- stylized but not toy-like
- expressive eyes without exaggerated childlike proportions

Avoid 3D drift toward:
- Pixar-like or Disney-like family animation
- rounded plush toy proportions
- chibi face shapes unless requested
- soft plastic material treatment
- exaggerated comedic expression style

## Simplifying Literary Prose

When the source is literary or poetic:

1. Extract what is actually visible.
2. Separate mood from visible acting or atmosphere.
3. Convert abstract emotion into observable state.
4. Decide whether the moment is better as narration support, anchor image, or motion clip.

Examples:
- `She felt the weight of her past closing in.`
  Better production language:
  `She pauses at the doorway, lowers her eyes, and tightens her grip on the helmet.`

- `The garage looked like a graveyard of broken ambition.`
  Better production language:
  `A dim garage packed with stripped frames, oil stains, hanging tools, and half-covered bikes.`

## Beat-to-Prompt Rules

- One beat may need both an anchor prompt and a video prompt.
- Some beats only need an anchor prompt.
- Some beats only need narration support.
- Not all beats deserve a full clip.
- If a beat contains multiple major actions, split the beat before prompt writing.
- Step 4 uses the strongest single-frame interpretation.
- Step 5 uses the strongest motion interpretation.
- Neither step should directly copy the narration line or flatten the beat into a schema-driven prompt.
