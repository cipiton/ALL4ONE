# Output Schema

Use these schemas when producing the package.

## 1. Narration Script

Required top-level fields:
- `project_title`
- `source_file`
- `structure_basis`
- `sections`

Each `sections[]` item requires:
- `section_id`
- `source_label`
- `summary`
- `narration_lines`

Notes:
- `structure_basis` should explain whether sections came from chapters, inferred sequences, or another clear source structure.
- `narration_lines` is an ordered array of spoken-ready lines.

Example shape:

```json
{
  "project_title": "Example Story",
  "source_file": "novel.txt",
  "structure_basis": "chapter headings from source",
  "sections": [
    {
      "section_id": "ch01",
      "source_label": "Chapter 1",
      "summary": "The rider returns to the factory town in a storm.",
      "narration_lines": [
        "She rides back into the town just before dawn.",
        "The storm turns the empty road into a tunnel of light and rain."
      ]
    }
  ]
}
```

## 2. Beat Sheet

Required top-level fields:
- `project_title`
- `beats`

Each `beats[]` item requires:
- `beat_id`
- `chapter_id`
- `beat_title`
- `summary`
- `story_function`
- `priority`
- `clip_worthy`
- `duration_class`
- `shot_type_suggestion`
- `camera_movement_suggestion`
- `mood`
- `subject_focus`
- `scene_focus`
- `prop_focus`
- `narration_anchor_line`
- `visual_core`
- `dramatic_focus`
- `continuity_notes`
- `emotional_pressure`
- `strongest_single_frame_interpretation`
- `strongest_motion_interpretation`
- `shot_design`
- `camera_intent`

Value guidance:
- `story_function`: `hook`, `development`, `turn`, `payoff`, `cliffhanger`, or `insert`
- `priority`: `high`, `medium`, or `low`
- `clip_worthy`: `yes`, `no`, or `maybe`
- `duration_class`: `short`, `medium`, or `long`
- The dramatization fields are planning fields, not final prompt text. They should capture the strongest visible beat interpretation, the dramatic pressure, continuity constraints, and shot/camera intent that Step 4 and Step 5 will render separately.

## 3. Asset Registry

Required top-level fields:
- `project_title`
- `assets`

Each `assets[]` item requires:
- `asset_id`
- `asset_type`
- `asset_name`
- `short_description`
- `recurrence_importance`
- `linked_beats`
- `generation_priority`
- `consistency_notes`

Value guidance:
- `asset_type`: `character`, `environment`, `prop`, `vehicle`, `wardrobe`, or `state_variant`
- `recurrence_importance`: `core`, `recurring`, or `supporting`
- `generation_priority`: `high`, `medium`, or `low`

## 4. Anchor Prompt Record

Required top-level fields:
- `anchor_prompts`

Each `anchor_prompts[]` item requires:
- `prompt_id`
- `beat_id`
- `linked_assets`
- `shot_size`
- `subject`
- `environment`
- `main_object`
- `composition`
- `lighting`
- `visible_state`
- `style`
- `anchor_image_prompt`

Rules:
- `anchor_image_prompt` must describe a single controllable frame.
- Keep it literal, visual, cinematic, and single-frame.
- It should be rendered from the beat's `strongest_single_frame_interpretation`, `shot_design`, `camera_intent`, `dramatic_focus`, `visual_core`, and `continuity_notes`, not assembled as a metadata list.
- If `visual_style` or `style` is `3D`, default the internal `3d_style_variant` to `anime_donghua_3d` and render the style as premium stylized East Asian 3D / cinematic donghua-inspired CG, not Pixar-like family animation.

## 5. Video Prompt Record

Required top-level fields:
- `video_prompts`

Each `video_prompts[]` item requires:
- `prompt_id`
- `beat_id`
- `linked_anchor_prompt_id`
- `linked_assets`
- `motion_focus`
- `environment_motion`
- `character_action`
- `camera_movement`
- `pacing`
- `video_prompt`

Rules:
- `video_prompt` assumes the anchor image already established the subject, scene, and style.
- The emphasis is what changes next, not restating static composition.
- It should be rendered from the beat's `strongest_motion_interpretation`, `camera_intent`, `continuity_notes`, and `emotional_pressure`, plus the linked anchor frame's visible state.
- It must feel like a continuation from the anchor frame, not a fresh scene rewrite.

## 6. Production Notes

Required fields:
- `coverage_gaps`
- `asset_risks`
- `prompt_risks`
- `recommended_next_steps`
