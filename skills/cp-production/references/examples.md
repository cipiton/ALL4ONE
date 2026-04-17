# Worked Example

## Source Prose

```text
Rain hammered the corrugated roof above the repair shed. Lin stood beside the bike with a wrench in her hand, listening to the engine cough and die again. She wiped the rain from her face, glanced toward the dark road, and made up her mind.
```

## Narration Line

```text
Under the repair shed, Lin listens to the dying engine one last time, then decides she cannot wait for daylight.
```

## Extracted Beats

```json
{
  "beats": [
    {
      "beat_id": "b01",
      "chapter_id": "ch01",
      "beat_title": "Engine dies under the shed",
      "summary": "Lin tests the bike under a rain-lashed repair shed and hears the engine fail again.",
      "story_function": "development",
      "priority": "high",
      "clip_worthy": "yes",
      "duration_class": "short",
      "shot_type_suggestion": "medium close-up",
      "camera_movement_suggestion": "slow push in",
      "mood": "tense, rain-soaked",
      "subject_focus": "Lin and the failing bike",
      "scene_focus": "repair shed in heavy rain",
      "prop_focus": "wrench, motorcycle",
      "narration_anchor_line": "Lin listens to the engine fail again."
    },
    {
      "beat_id": "b02",
      "chapter_id": "ch01",
      "beat_title": "Decision to leave",
      "summary": "Lin wipes rain from her face, checks the road, and chooses to move.",
      "story_function": "turn",
      "priority": "high",
      "clip_worthy": "yes",
      "duration_class": "short",
      "shot_type_suggestion": "close-up",
      "camera_movement_suggestion": "static frame then slight push in",
      "mood": "resolved, restrained",
      "subject_focus": "Lin's visible decision",
      "scene_focus": "shed opening toward the road",
      "prop_focus": "wrench in hand",
      "narration_anchor_line": "She makes her decision before daylight comes."
    }
  ]
}
```

## Extracted Assets

```json
{
  "assets": [
    {
      "asset_id": "char_lin",
      "asset_type": "character",
      "asset_name": "Lin",
      "short_description": "Young mechanic, rain-soaked, practical, physically worn but controlled.",
      "recurrence_importance": "core",
      "linked_beats": ["b01", "b02"],
      "generation_priority": "high",
      "consistency_notes": "Keep face, build, wet hair, and workwear consistent across rain scenes."
    },
    {
      "asset_id": "env_repair_shed",
      "asset_type": "environment",
      "asset_name": "Roadside repair shed",
      "short_description": "Open-sided metal shed with corrugated roof, tools, pooled water, and a dark road beyond.",
      "recurrence_importance": "recurring",
      "linked_beats": ["b01", "b02"],
      "generation_priority": "high",
      "consistency_notes": "Maintain roof texture, tool clutter, puddles, and road orientation."
    }
  ]
}
```

## Anchor Prompt

```json
{
  "prompt_id": "a01",
  "beat_id": "b01",
  "linked_assets": ["char_lin", "env_repair_shed"],
  "shot_size": "medium close-up",
  "subject": "Lin beside the motorcycle",
  "environment": "open-sided repair shed in hard rain at night",
  "main_object": "wrench and rain-wet motorcycle engine",
  "composition": "Lin in the left third, bike engine in the foreground, dark road visible beyond the shed opening",
  "lighting": "single harsh work light with wet reflections on metal and concrete",
  "visible_state": "wet hair, soaked work jacket, listening posture, engine just failed",
  "style": "grounded cinematic realism",
  "anchor_image_prompt": "Medium close-up of Lin beside a rain-wet motorcycle under an open-sided repair shed at night, wrench still in one hand, listening to the dead engine. Lin stands in the left third of frame while the engine housing fills the foreground and the dark road opens behind her. A single harsh work light throws sharp reflections across wet metal, puddled concrete, and the corrugated roof. Grounded cinematic realism."
}
```

## Video Prompt

```json
{
  "prompt_id": "v01",
  "beat_id": "b02",
  "linked_anchor_prompt_id": "a01",
  "linked_assets": ["char_lin", "env_repair_shed"],
  "motion_focus": "decision moment",
  "environment_motion": "rain sheets past the shed opening and drips from the roof edge",
  "character_action": "Lin wipes rain from her face, glances toward the road, then tightens her grip on the wrench",
  "camera_movement": "slow push in",
  "pacing": "restrained, building resolve",
  "video_prompt": "Lin wipes the rain from her face, looks toward the dark road, then tightens her grip on the wrench as she decides to move. Rain keeps streaming past the shed opening and dripping from the roof edge. The camera slowly pushes in to hold on the moment her posture firms."
}
```

## Why The Outputs Differ

- The narration line explains the moment.
- The beat records why the moment matters and how to stage it.
- The anchor prompt locks a usable still composition.
- The video prompt focuses on what moves next and how the camera responds.
