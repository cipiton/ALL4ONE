# Prompt Policy

## Core Rule

Narrative source text is planning material. It is not a final FLUX prompt.

The LLM should derive the final prompt from structured assets, beats, and anchor planning, not by dumping prose into the image model. Python should only orchestrate and provide a deterministic fallback when LLM prompt authoring fails.

## Asset Prompts

Asset prompts produce one reusable reference image at a time.

They should emphasize:

- the single subject
- stable identity or design
- clean composition
- readable lighting
- reusable style consistency

They should avoid:

- montage wording
- multi-stage action
- recap narration
- story-summary language
- symbolic or poetic filler that weakens controllability

## Keyscene Prompts

Keyscene prompts produce one integrated still-image story instant.

They should emphasize:

- the main dramatic relation in the frame
- the selected shot size
- the specific blocking between subject and environment
- the chosen reference roles
- compact style language

They should avoid:

- video-motion phrasing as if FLUX were a video model
- re-describing every trait already present in the references
- overlong recap-like plot explanation
- forcing three references when two are enough

## Language Policy

- Final FLUX prompts must be rendered in exactly one language.
- Use `[generation] final_prompt_language` from `config.ini`.
- Supported values are `en` and `zh`.
- If the setting is missing or invalid, fall back to `en`.

## Source Separation

Keep these layers separate:

- source understanding
- structured prompt fields
- final prompt rendering

The deterministic prompt builder may use structured fields from recap-production or cp-production, but the final rendered prompt should remain concise and model-facing.
