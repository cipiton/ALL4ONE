import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

import torch
from diffusers import Flux2KleinPipeline
from diffusers.utils import load_image
from PIL import Image

MODEL_MAP = {
    "4b": "black-forest-labs/FLUX.2-klein-4B",
    "9b": "black-forest-labs/FLUX.2-klein-9B",
}

DEFAULT_STEPS = {
    "4b": 4,
    "9b": 4,
}

CONTENT_PRESETS = {
    "character_scene": (
        "Place the same character from the reference image into this scene. "
        "Keep the character identity, clothing, and hairstyle from the character reference. "
        "Keep the environment, lighting, perspective, and composition from the scene image. "
        "Natural full-body placement. "
        "Do not add extra people, extra vehicles, or text."
    ),
    "character_prop_scene": (
        "Place the same character from the reference image into this scene beside the same vehicle or prop from the prop reference. "
        "Keep the character identity, clothing, and hairstyle from the character reference. "
        "Keep the prop design from the prop reference. "
        "Keep the environment, lighting, perspective, and composition from the scene image. "
        "Natural scale and coherent placement. "
        "Do not add extra people, extra props, or text."
    ),
    "riding": (
        "Place the same character from the reference image riding or interacting naturally with the same vehicle or prop from the prop reference in this scene. "
        "Keep the character identity, clothing, and hairstyle from the character reference. "
        "Keep the prop design from the prop reference. "
        "Keep the environment, lighting, perspective, and composition from the scene image. "
        "Do not add extra people, extra props, or text."
    ),
    "portrait_insert": (
        "Place the same character from the reference image into this scene. "
        "Prioritize character identity and clean integration. "
        "Keep the scene framing and background from the scene image. "
        "Do not add extra people, extra props, or text."
    ),
}

STYLE_PRESETS = {
    "2d_anime": (
        "Use a clean 2D anime illustration style. "
        "Preserve anime facial design, line-art feel, cel-shaded coloring, and simplified illustrated forms. "
        "Not photorealistic, not 3D rendered, not CGI, not doll-like."
    ),
    "3d_anime": (
        "Use a polished 3D anime style. "
        "Preserve anime facial proportions and stylized character design, but render with dimensional lighting, smooth materials, and high-quality anime 3D shading. "
        "Not photorealistic live-action."
    ),
    "realism": (
        "Use a grounded cinematic realistic style. "
        "Natural materials, realistic lighting, believable proportions, and realistic surface detail. "
        "Not cel-shaded, not cartoon, not anime line-art."
    ),
}

SCENE_HINT_PRESETS = {
    "none": "",
    "rainy_road": (
        "Rainy mountain road, wet asphalt, foggy hills, overcast lighting, cool desaturated tones."
    ),
    "garage": (
        "Dim garage interior, practical lighting, workshop clutter, grounded perspective, moody shadows."
    ),
    "gas_station": (
        "Roadside gas station environment, practical lighting, grounded layout, believable scale."
    ),
}

NEGATIVE_HINTS = {
    "2d_anime": "no photorealism, no CGI, no plastic skin, no live-action look, no extra people, no text",
    "3d_anime": "no live-action realism, no messy proportions, no extra people, no text",
    "realism": "no cel shading, no cartoon look, no anime line-art, no extra people, no text",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified FLUX.2 klein multi-reference test")

    parser.add_argument("--scene", help="Path to scene image")
    parser.add_argument("--character", help="Path to character image")
    parser.add_argument("--prop", help="Path to prop image")
    parser.add_argument("--output", default="test_flux2_klein.png", help="Output image path")
    parser.add_argument("--batch-file", help="Optional JSON batch file describing multiple jobs")

    parser.add_argument("--model-size", choices=["4b", "9b"], default="4b", help="Choose klein model size")
    parser.add_argument("--model", help="Optional explicit model ID override")

    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, help="Inference steps; defaults depend on model size")
    parser.add_argument("--guidance", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)

    parser.add_argument("--prompt", help="Full custom prompt text")
    parser.add_argument("--prompt-file", help="Path to a text file containing the prompt")

    parser.add_argument(
        "--content-preset",
        choices=sorted(CONTENT_PRESETS.keys()),
        default="character_prop_scene",
        help="Shot/content preset",
    )
    parser.add_argument(
        "--style-preset",
        choices=sorted(STYLE_PRESETS.keys()),
        default="2d_anime",
        help="Rendering style preset",
    )
    parser.add_argument(
        "--scene-hint",
        choices=sorted(SCENE_HINT_PRESETS.keys()),
        default="none",
        help="Optional extra environment hint",
    )

    return parser.parse_args()


def load_and_resize(path: str, width: int, height: int) -> Image.Image:
    image = load_image(path)
    return image.resize((width, height))


def build_reference_images(args: argparse.Namespace) -> List[Image.Image]:
    refs: List[Image.Image] = []
    if args.scene:
        refs.append(load_and_resize(args.scene, args.width, args.height))

    if args.character:
        refs.append(load_and_resize(args.character, args.width, args.height))

    if args.prop:
        refs.append(load_and_resize(args.prop, args.width, args.height))

    return refs


def resolve_model(args: argparse.Namespace) -> str:
    if args.model:
        return args.model
    return MODEL_MAP[args.model_size]


def resolve_steps(args: argparse.Namespace) -> int:
    if args.steps is not None:
        return args.steps
    return DEFAULT_STEPS[args.model_size]


def build_preset_prompt(args: argparse.Namespace) -> str:
    parts = [
        CONTENT_PRESETS[args.content_preset],
        STYLE_PRESETS[args.style_preset],
    ]

    scene_hint = SCENE_HINT_PRESETS[args.scene_hint]
    if scene_hint:
        parts.append(scene_hint)

    negative_hint = NEGATIVE_HINTS[args.style_preset]
    if negative_hint:
        parts.append(negative_hint)

    return " ".join(part.strip() for part in parts if part.strip())


def resolve_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt.strip()
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return build_preset_prompt(args)


def main() -> None:
    configure_utf8_console()
    args = parse_args()
    if args.batch_file:
        run_batch(args.batch_file)
        return
    run_single(args)


def run_single(args: argparse.Namespace) -> None:
    model_id = resolve_model(args)
    steps = resolve_steps(args)
    prompt = resolve_prompt(args)
    pipe = load_pipeline(model_id)
    references = build_reference_images(args)
    safe_print(f"Using {len(references)} reference image(s):")
    if args.scene:
        safe_print(f"  scene: {args.scene}")
    if args.character:
        safe_print(f"  character: {args.character}")
    if args.prop:
        safe_print(f"  prop: {args.prop}")

    safe_print(f"Model size: {args.model_size}")
    safe_print(f"Resolution: {args.width}x{args.height}")
    safe_print(f"Steps: {steps}")
    safe_print(f"Guidance: {args.guidance}")
    safe_print(f"Seed: {args.seed}")
    safe_print(f"Content preset: {args.content_preset}")
    safe_print(f"Style preset: {args.style_preset}")
    safe_print(f"Scene hint: {args.scene_hint}")
    safe_print(f"Prompt: {prompt}")

    render_job(
        pipe=pipe,
        prompt=prompt,
        references=references,
        width=args.width,
        height=args.height,
        guidance=args.guidance,
        steps=steps,
        seed=args.seed,
        output_path=args.output,
    )
    safe_print(f"Saved: {args.output}")


def run_batch(batch_file: str) -> None:
    payload = json.loads(open(batch_file, "r", encoding="utf-8").read())
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list) or not jobs:
        raise ValueError(f"Batch file must contain a non-empty `jobs` array: {batch_file}")

    current_model_id = None
    pipe = None
    model_load_count = 0
    for index, job in enumerate(jobs, start=1):
        if not isinstance(job, dict):
            raise ValueError(f"Batch job {index} must be a JSON object.")
        model_id = str(job.get("model") or MODEL_MAP["4b"]).strip()
        if model_id != current_model_id:
            current_model_id = model_id
            pipe = load_pipeline(model_id)
            model_load_count += 1
        assert pipe is not None
        width = int(job.get("width") or 768)
        height = int(job.get("height") or 512)
        steps = int(job.get("steps") or DEFAULT_STEPS["4b"])
        guidance = float(job.get("guidance") or 1.0)
        seed = int(job.get("seed") or 42)
        prompt = str(job.get("prompt") or "").strip()
        output_path = str(job.get("output") or "").strip()
        if not prompt:
            raise ValueError(f"Batch job {index} is missing a prompt.")
        if not output_path:
            raise ValueError(f"Batch job {index} is missing an output path.")
        references = build_reference_images_from_paths(
            scene=job.get("scene"),
            character=job.get("character"),
            prop=job.get("prop"),
            width=width,
            height=height,
        )
        label = job.get("job_id") or f"{index}/{len(jobs)}"
        safe_print(f"Batch job {label}: {Path(output_path).name}")
        safe_print(f"  model: {model_id}")
        safe_print(f"  refs: {len(references)}")
        render_job(
            pipe=pipe,
            prompt=prompt,
            references=references,
            width=width,
            height=height,
            guidance=guidance,
            steps=steps,
            seed=seed,
            output_path=output_path,
        )
        safe_print(f"[x] completed {index}/{len(jobs)}: {Path(output_path).name}")
    safe_print(f"Batch complete. Models loaded: {model_load_count}")


def load_pipeline(model_id: str) -> Flux2KleinPipeline:
    safe_print(f"Loading model: {model_id}")
    pipe = Flux2KleinPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
    )
    pipe.enable_model_cpu_offload()
    return pipe


def build_reference_images_from_paths(
    *,
    scene: str | None,
    character: str | None,
    prop: str | None,
    width: int,
    height: int,
) -> List[Image.Image]:
    refs: List[Image.Image] = []
    if scene:
        refs.append(load_and_resize(str(scene), width, height))
    if character:
        refs.append(load_and_resize(str(character), width, height))
    if prop:
        refs.append(load_and_resize(str(prop), width, height))
    return refs


def render_job(
    *,
    pipe: Flux2KleinPipeline,
    prompt: str,
    references: List[Image.Image],
    width: int,
    height: int,
    guidance: float,
    steps: int,
    seed: int,
    output_path: str,
) -> None:
    generator_device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = torch.Generator(device=generator_device).manual_seed(seed)
    result = pipe(
        prompt=prompt,
        image=references if references else None,
        width=width,
        height=height,
        guidance_scale=guidance,
        num_inference_steps=steps,
        generator=generator,
    ).images[0]
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    result.save(output_path)


def configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                continue


def safe_print(message: str) -> None:
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()
