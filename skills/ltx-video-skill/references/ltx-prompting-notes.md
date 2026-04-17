# LTX Prompting Notes

This skill builds one shot prompt per recap beat for later LTX clip generation. The prompt shape is based on the official LTX 2.3 guides:

- `https://ltx.io/model/model-blog/ltx-2-3-prompt-guide`
- `https://docs.ltx.video/api-documentation/prompting-guide`

## Core Rule

Describe what the viewer should literally see happening next, not what the story means.

## Official Prompt Shape Applied Here

- one beat becomes one shot prompt
- the final prompt is a single flowing paragraph
- default length is roughly 4-8 descriptive sentences, adjusted by shot mode and duration
- action is written as a sequence from opening state to end of shot
- prompts stay in present-tense Chinese phrasing
- camera behavior is explicit relative to the subject
- audio is optional and only added when it helps motion readability
- image-to-video prompts bias toward what moves next instead of re-describing static setup

## Internal Structured Fields

The prompt director works through structured fields before assembling the final paragraph:

- `shot_type`
- `shot_mode`
- `scene_setup`
- `character_definition`
- `action_sequence`
- `camera_motion`
- `environment_motion`
- `audio_description`
- `acting_cues`
- `duration_hint`
- `final_prompt`

## Shot Modes

- `closeup_emotion`: face, breath, eyes, hand detail, restrained environment detail
- `dialogue_speaking`: visible speaking action, lip movement, pauses, eye lines, optional dialogue-relevant audio
- `insert_prop_detail`: prop or mechanism detail, tight camera phrasing, only local motion that matters
- `staging_environment`: space-first blocking, clear relationship between subject and location
- `action_movement`: stronger movement progression, secondary motion, clearer follow camera or static-frame choice

## Patterns To Avoid

- recap narration or summary voice
- thematic explanation, symbolism, destiny, or “what it represents”
- static one-line prompts that only restate the beat
- emotion labels without visible acting cues
- overloaded scenes with too many actions or conflicting light logic
- readable text, logos, or unnecessary brand details
- re-describing image content that would already be visible in the source frame

## Motion Progression Rule

Each final prompt should usually include:

1. opening state
2. primary movement or change
3. secondary motion or reaction
4. camera behavior during or after the action

## Validation Rules

The validator treats these as warning or fallback triggers:

- missing required fields
- non-paragraph output
- sentence counts outside the shot-mode range
- no visible action progression
- no camera language or static-frame choice
- recap-like phrasing
- slideshow-like patterns
- abstract emotion without acting cues
- mixed-language leakage in the final Chinese prompt
- malformed JSON

## Debug Artifacts

Per shot debug JSON keeps:

- source beat text
- the exact request payload sent to Gemini
- structured intermediate fields
- raw Gemini response text and parsed JSON
- validation result
- final prompt
- fallback reason when fallback was used

## Future v2 Direction

v2 can later reuse the saved prompt pack together with:

- keyframes or keyscenes
- clip duration planning
- LTX render configuration
- clip stitching and retry logic
