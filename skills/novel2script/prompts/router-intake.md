Classify the intake request and return STRICT JSON ONLY.

You are routing a Chinese short-drama workflow intake.

Decide:
- `start_step`
- `input_key`
- `preprocess`
- `reason`

Return exactly one JSON object with this schema:
{
  "start_step": "step1",
  "input_key": "user_brief",
  "preprocess": "story_bible",
  "reason": "The file appears to be a raw novel and the user wants end-to-end script generation."
}

Allowed values:
- `start_step`: `step1`, `step2`, `step3`, `step4`, `step5`, `step6`, `step7`
- `input_key`: `user_brief`, `story`, `episode_outline`, `episode_scripts`, `analysis`, `assets`
- `preprocess`: `none`, `story_bible`

Routing rules:
- Raw novel, prose, or story text plus a request for end-to-end generation: `step1`, `user_brief`, `story_bible`
- Story synopsis plus a request for episode plot: `step2`, `story`, `none`
- Scenes or episode outline plus a request for screenplay: `step4`, `episode_outline`, `none`
- Full script plus a request for analysis: `step5`, `episode_scripts`, `none`
- Full script plus a request for asset extraction: `step6`, `episode_scripts`, `none`
- Assets plus a request for image config: `step7`, `assets`, `none`

If ambiguous:
- Choose the earliest valid step that makes sense.
- Do not skip required prerequisites unless the input already appears to contain the equivalent upstream artifact.

Output rules:
- Return JSON only.
- Do not wrap the JSON in markdown fences.
- Do not add any text before or after the JSON.
