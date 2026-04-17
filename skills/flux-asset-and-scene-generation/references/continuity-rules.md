# Continuity Rules

## Assets

Generate assets as reusable continuity anchors.

- Characters should preserve identity, silhouette, wardrobe logic, and facial recognition cues.
- Props should preserve shape, material, and design-critical details.
- Scenes should preserve layout, light logic, and environmental read.

## Keyscenes

Use the smallest reliable reference set.

- Default to `scene + character` for most beats.
- Prefer `scene + prop` for insert or object-driven beats.
- Use `scene + character + prop` only when the prop is story-critical and the match is strong enough.

## Vehicles And Large Props

- Avoid poster-like oversizing.
- Prefer scene and rider continuity first.
- Only include the vehicle prop reference when it improves control without breaking scale.

## Reuse Policy

Reuse existing generated assets when:

- they already satisfy the current continuity need
- the user wants to continue a previous run
- regenerating them would not improve the result meaningfully

Regenerate assets when:

- the user explicitly asks for regeneration
- the requested workflow is `assets -> keyscenes`
- the required asset group is missing
- the available references are too weak for reliable keyscene continuity

## Stop Conditions

Stop clearly when:

- keyscenes are requested but no usable generated assets exist and no asset source is available
- assets are requested but the structured asset source is missing
- the source contract is too incomplete to maintain continuity honestly
