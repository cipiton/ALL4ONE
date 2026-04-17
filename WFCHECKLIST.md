# workflow Skill Test Checklist

- [x] Change output structure first
- [x] Create T2I skill
- [x] Build I2I script
- [x] Wrap I2I into skill
- [ ] Build FLF2V script
- [ ] Wrap FLF2V into skill

two codex prompts to input
-----------------------------------------------------------------------------------------------------------------------------
1. Edit the existing FLUX asset/keyscene generation skill and pipeline.

Goal:
Standardize the final generation prompts so they default to English, and add a config.ini option that lets users choose the final prompt language:
- `en`
- `zh`

Important:
- Update tasks.md as you work.
- Check off completed tasks with brief evidence for each completed item.
- Do not stop at planning. Implement the changes.
- After implementation, summarize exactly what changed, why, and how to test it.

Current problem:
The pipeline currently mixes Chinese and English in final generation prompts. This likely contributes to drift and weaker control.
The source content can remain Chinese, but the final prompt sent into generation should be rendered in one language only.
Default this to English, because the current system is now mostly English-facing.

Required behavior:
1. Add a config.ini option for final prompt language, something like:
   - `final_prompt_language = en`
   Supported values:
   - `en`
   - `zh`

2. Default behavior:
   - if the setting is missing, default to `en`

3. Scope:
   - apply this to final prompts used for:
     - asset generation
     - keyscene generation
   - do not break existing source-language handling
   - source script / metadata / internal beat extraction can remain in Chinese or bilingual form if needed
   - only the final model-facing prompt should be controlled by this setting

4. Prompt rendering policy:
   - keep upstream understanding/extraction logic unchanged where possible
   - keep structured internal shot/asset fields language-neutral if possible
   - render the final generation prompt in exactly one language based on config.ini
   - do not mix Chinese and English in the final rendered prompt

5. English mode:
   - render all final prompts fully in English
   - convert style, shot, scale, mood, and scene instructions into English
   - keep names sensible and stable

6. Chinese mode:
   - render all final prompts fully in Chinese
   - do not leak English camera/style keywords into the final Chinese prompt unless there is a strong technical reason and it is documented

7. Implementation preference:
   - separate:
     - source understanding
     - structured prompt fields
     - final prompt rendering
   - add a small prompt-rendering layer/function if needed, rather than scattering language conditionals everywhere

8. Validation:
   - validate config value
   - if invalid, warn and fall back to `en`

9. Debug / manifest:
   - record the selected final prompt language in debug output and/or manifest
   - for each generated image, store:
     - source/structured input
     - final rendered prompt
     - final prompt language

10. Backward compatibility:
   - do not break old runs
   - if config is absent, use English and continue

Files likely to touch:
- config loading logic
- prompt builder / prompt rendering code
- asset generation prompt builder
- keyscene generation prompt builder
- documentation / README / SKILL.md if applicable
- tasks.md

Testing requirements:
1. Test asset generation prompt rendering in:
   - English
   - Chinese
2. Test keyscene prompt rendering in:
   - English
   - Chinese
3. Verify final rendered prompts are single-language only
4. Verify invalid config falls back to English
5. Verify default behavior without the setting uses English

Deliverables:
- updated code
- updated config handling
- updated tasks.md
- brief implementation summary
- brief testing summary
- any caveats

Important quality bar:
Do not translate raw source text blindly at the start of the pipeline.
Keep source understanding separate from final prompt rendering.
The change should specifically make the final model-facing prompts single-language and configurable.
--------------------------------------------------------------------------------------------------------------------------------
2. Update the existing `ltx-video-skill` so its prompt generation follows the official LTX 2.3 prompting guides more closely and reduces slideshow-like outputs.

Context:
- V1 already reads recap production output and uses Gemini (`gemini = google/gemini-2.5-flash` in config.ini) to generate prompts.
- Current prompts are still too weak and produce slideshow-like videos.
- Do not change the overall purpose of the skill.
- Update tasks.md as you work. Check off completed tasks with brief evidence for each completed item.
- Do not stop at planning. Implement the changes.
- After implementation, summarize exactly what changed, why, and how to test it.

Use these official guides as the source of truth for prompt design:
- https://ltx.io/model/model-blog/ltx-2-3-prompt-guide
- https://docs.ltx.video/api-documentation/prompting-guide

Key guidance to apply from the docs:
- Prompts should be a single flowing paragraph.
- Use present tense verbs for action and movement.
- Include: shot, scene, action, character, camera movement, and audio when relevant.
- Match detail to shot scale.
- Aim for roughly 4–8 descriptive sentences.
- For image-to-video, focus on what happens next rather than re-describing static elements already visible.
- Use visual cues instead of abstract emotional labels.
- Avoid overloaded scenes, conflicting lighting, complex physics, readable text/logos, and overcomplicated prompts.
- Clear camera language helps.
- Write the action as a natural sequence from beginning to end.

Main problem to solve:
The current prompts are too recap-like and not shot-like enough, so they under-direct motion and become slideshow-like.

Implement these changes:

1. Refactor Gemini prompt-generation instructions
Rewrite the Gemini system/developer prompt used by the skill so it explicitly transforms recap beats into LTX-2.3-style shot prompts.

The Gemini instruction must enforce:
- one shot = one prompt
- one coherent flowing paragraph
- 4–8 descriptive sentences by default
- present-tense action
- visible action sequence from beginning to end
- physical acting cues instead of abstract emotional words
- camera movement relative to the subject
- optional audio/ambient sound only when useful
- no recap narration
- no thematic summary language
- no “story meaning” filler
- no describing static image details again unless needed for clarity

2. Add a stronger structured intermediate schema
Before final prompt assembly, generate structured fields such as:
- shot_type
- scene_setup
- character_definition
- action_sequence
- camera_motion
- environment_motion
- audio_description
- acting_cues
- duration_hint
- final_prompt

Keep this schema internal, but use it to improve reliability.

3. Add shot-aware prompt generation modes
At minimum support these internal modes:
- close-up / emotion shot
- dialogue / speaking shot
- insert / prop detail shot
- staging / environment shot
- action / movement shot

Each mode should influence:
- amount of visual detail
- camera language
- whether audio is included
- level of acting detail

4. Add explicit image-to-video behavior
When the skill is generating prompts for image-to-video use cases, it must bias toward:
- what moves next
- how the camera moves
- what secondary motion happens
- what sound emerges
and avoid re-describing static scene setup too heavily.

5. Remove slideshow-causing prompt patterns
Reduce or eliminate prompts that are:
- too short for the clip duration
- too static
- recap-style summaries
- mostly emotional interpretation without visible actions
- lacking camera movement
- lacking motion progression

Add validation rules to flag prompts that look like:
- “character is in a place and feels X”
without enough concrete motion.

6. Add motion progression logic
Each final prompt should generally include:
- opening state
- primary movement/change
- optional secondary movement/reaction
- camera behavior during or after the action

Make this a real sequence, not just a static description.

7. Improve camera language generation
Generate clearer camera instructions such as:
- slow push in
- handheld tracking from behind
- pan right revealing…
- static frame as…
- tilt upward to reveal…
- over-the-shoulder as…
Only use camera moves when they help the shot.

8. Add acting-cue generation
For human beats, convert abstract emotion into visible cues:
- pauses
- glances
- head turns
- tightening grip
- lowered gaze
- breath
- small body shifts
- lip movement for dialogue
Avoid generic labels like “sad” unless converted into something visible.

9. Add optional audio fields
If the beat clearly implies audio, include short useful audio cues:
- rain on metal roof
- welding sparks crackling
- motorcycle engine revving
- distant crowd cheering
- muffled room tone
Do not overload every prompt with audio.

10. Add prompt validation and fallback improvement
Validate generated prompts for:
- paragraph form
- sentence count range
- presence of visible action
- presence of camera or clear static-frame choice
- absence of recap-summary phrasing
- not too short for longer clips
- no mixed-language final prompt if your current prompt language policy is enabled

If Gemini output fails validation:
- log why
- run a deterministic fallback builder that still follows the LTX prompt rules better than the old version

11. Add debug output
Per shot, save:
- source beat text
- structured intermediate fields
- raw Gemini response
- validation result
- final prompt
- fallback reason if applicable

12. Update documentation
Update SKILL.md / README / references so the skill explains:
- that it now follows official LTX 2.3 prompting guidance
- how prompts are structured
- how image-to-video prompting differs from recap text
- what kinds of prompt patterns are avoided
- what debug artifacts are written

13. Keep scope contained
Do not implement actual video generation yet unless tiny changes are needed for test harnesses.
The focus is improving prompt quality for the later LTX stage.

Testing requirements:
1. Test at least 3 representative beats:
- subtle emotion / close-up
- dialogue or speaking beat
- action or environment beat
2. Show before/after prompts for each.
3. Verify new prompts are:
- single-paragraph
- present tense
- 4–8 sentences when appropriate
- more motion-directed
- less recap-like
4. Verify image-to-video prompts focus on what happens next.
5. Verify validation catches at least one weak/slideshow-like prompt.
6. Run one real folder through the updated prompt generator and summarize quality improvement.

Deliverables:
- updated skill files
- updated tasks.md
- implementation summary
- testing summary
- caveats / next steps