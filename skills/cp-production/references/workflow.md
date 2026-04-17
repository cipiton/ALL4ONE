# CP Production Workflow

## Five Layers

This skill converts raw story prose into five production layers:

1. Story layer
- Source: `novel.txt`
- Goal: preserve narrative order, dramatic arc, character progression, and key reveals
- Output: narration-ready script

2. Beat layer
- Source: narration script plus raw story structure
- Goal: break the story into production-useful beats instead of paragraph-sized prose chunks
- Output: beat sheet with priorities, functions, shot suggestions, and cinematic scene dramatization fields

3. Asset layer
- Source: beats plus recurring story details
- Goal: extract reusable generation targets so character, environment, and prop consistency is not rebuilt from scratch every beat
- Output: asset registry and generation plan

4. Scene dramatization layer
- Source: beat sheet plus continuity and asset context
- Goal: turn each beat into a strong scene-planning object before any final prompt is written
- Output: internal planning fields such as `visual_core`, `dramatic_focus`, `continuity_notes`, `strongest_single_frame_interpretation`, `strongest_motion_interpretation`, `shot_design`, and `camera_intent`

5. Prompt layer
- Source: beats plus linked assets
- Goal: render stage-specific prompts instead of recycling narration or recap prose
- Output: anchor image prompts for FLUX.2 klein and motion-first video prompts for LTX-2

## Practical Workflow

1. Read the raw story
- Detect chapters, sections, time jumps, and major location shifts.
- Preserve order.
- Do not collapse the story into a generic synopsis before analysis.

2. Create the narration script
- Rewrite for spoken clarity.
- Keep emotional content, but express it as narration, not prompt language.
- Organize by chapter, episode, or sequence depending on the source structure.

3. Extract beats
- Break long prose passages into multiple production beats.
- Separate hooks, developments, turns, payoffs, inserts, and cliffhangers.
- Decide whether each beat is clip-worthy, anchor-worthy, or mostly narration support.
- For every beat, decide the most compelling visible moment, the dramatic pressure, what must remain continuous, the strongest still-frame interpretation, and the strongest motion continuation.

4. Extract assets
- Group recurring elements into reusable characters, environments, props, vehicles, wardrobe variants, and age/state variants.
- Link each asset to the beats where it matters.
- Mark priority so downstream image generation focuses on high-impact assets first.

5. Generate anchor prompts
- Use the beat plus linked assets to create still-image anchor prompts.
- Render from the beat's scene dramatization instead of field-by-field prompt assembly.
- Emphasize visible composition, shot size, lighting, environment, subjects, stable style, dramatic focus, and continuity cues.
- Each prompt should describe a controllable single frame, not a sequence.
- If the selected style is 3D, default to `anime_donghua_3d`: premium stylized East Asian CG / cinematic donghua-inspired 3D, not Pixar-like rounded family animation.

6. Generate video prompts
- Use the same beat plus anchor context to create LTX-2 prompts.
- Focus on what moves next, who moves, what secondary motion happens, and how the camera behaves.
- Keep the prompt shorter and more motion-driven than the anchor prompt.
- Treat each video prompt as the natural continuation of the linked anchor frame, preserving identity, wardrobe, location, prop state, style, and emotional continuity.

## Separation Rules

- Story prose is not prompt text.
- Narration script is not prompt text.
- Beat summaries are planning artifacts, not prompt text.
- Scene dramatization fields are prompt design inputs, not a separate merged output artifact.
- Anchor prompts and video prompts must be rendered from beats and assets, not copied from narration lines.

## Decision Heuristics

- If a moment is visually defining but mostly static, prioritize an anchor prompt.
- If a moment contains visible progression, reaction, or environmental change, add a video prompt.
- If a beat exists mainly to carry information, it may need narration support only.
- If a paragraph contains several major actions, split them into multiple beats before any prompt generation.
