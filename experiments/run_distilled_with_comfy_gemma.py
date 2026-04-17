from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent
LTX_ROOT = REPO_ROOT / "LTX-2"
for relative_path in ("packages/ltx-core/src", "packages/ltx-pipelines/src"):
    import_path = str((LTX_ROOT / relative_path).resolve())
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from comfy_gemma_bridge import (  # noqa: E402
    DEFAULT_DISTILLED_CHECKPOINT,
    DEFAULT_GEMMA_ROOT,
    DEFAULT_IMAGE,
    DEFAULT_OUTPUT,
    DEFAULT_PROMPT,
    DEFAULT_SPATIAL_UPSAMPLER,
    ComfyStyleGemmaPromptEncoder,
    install_cpu_safe_gpu_model_patch,
)
from ltx_pipelines.distilled import DistilledPipeline  # noqa: E402
from ltx_pipelines.utils.args import ImageAction, ImageConditioningInput, resolve_path  # noqa: E402
from ltx_pipelines.utils.helpers import get_device  # noqa: E402
from ltx_pipelines.utils.media_io import encode_video  # noqa: E402
from ltx_core.model.video_vae import TilingConfig, get_video_chunks_number  # noqa: E402


LOGGER = logging.getLogger("run_distilled_with_comfy_gemma")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone LTX distilled experiment that swaps the stock Gemma loader for a ComfyUI-LTXVideo-style loader."
    )
    parser.add_argument("--distilled-checkpoint-path", default=DEFAULT_DISTILLED_CHECKPOINT, type=resolve_path)
    parser.add_argument("--gemma-root", default=DEFAULT_GEMMA_ROOT, type=resolve_path)
    parser.add_argument("--spatial-upsampler-path", default=DEFAULT_SPATIAL_UPSAMPLER, type=resolve_path)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT, type=resolve_path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=192)
    parser.add_argument("--num-frames", type=int, default=17)
    parser.add_argument("--frame-rate", type=float, default=8.0)
    parser.add_argument("--enhance-prompt", action="store_true")
    parser.add_argument("--encode-only", action="store_true", help="Only run the Comfy-style prompt encoding bridge and print shapes.")
    parser.add_argument(
        "--image",
        dest="images",
        action=ImageAction,
        nargs="+",
        metavar="IMAGE_ARGS",
        default=[ImageConditioningInput(path=resolve_path(DEFAULT_IMAGE), frame_idx=0, strength=1.0)],
        help="Image conditioning arguments: PATH FRAME_IDX STRENGTH [CRF]. Can be repeated.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    args = build_parser().parse_args()

    install_cpu_safe_gpu_model_patch()

    device = get_device()
    dtype = torch.bfloat16
    LOGGER.info("Experiment root: %s", REPO_ROOT)
    LOGGER.info("LTX repo: %s", LTX_ROOT)
    LOGGER.info("Gemma model root: %s", args.gemma_root)
    LOGGER.info("Distilled checkpoint: %s", args.distilled_checkpoint_path)
    LOGGER.info("Spatial upsampler: %s", args.spatial_upsampler_path)
    LOGGER.info("Image conditioning: %s", args.images)
    LOGGER.info(
        "Inference settings: width=%s height=%s num_frames=%s frame_rate=%s seed=%s device=%s dtype=%s",
        args.width,
        args.height,
        args.num_frames,
        args.frame_rate,
        args.seed,
        device,
        dtype,
    )

    prompt_encoder = ComfyStyleGemmaPromptEncoder(
        checkpoint_path=args.distilled_checkpoint_path,
        gemma_root=args.gemma_root,
        dtype=dtype,
        device=device,
    )

    if args.encode_only:
        LOGGER.info("Running encode-only bridge check.")
        encoded = prompt_encoder.encode_only(args.prompt)
        LOGGER.info(
            "Encode-only success: video_shape=%s audio_shape=%s mask_shape=%s",
            tuple(encoded.video_encoding.shape),
            tuple(encoded.audio_encoding.shape) if encoded.audio_encoding is not None else None,
            tuple(encoded.attention_mask.shape),
        )
        return 0

    LOGGER.info("Building stock DistilledPipeline and replacing prompt_encoder with Comfy-style bridge.")
    pipeline = DistilledPipeline(
        distilled_checkpoint_path=args.distilled_checkpoint_path,
        gemma_root=args.gemma_root,
        spatial_upsampler_path=args.spatial_upsampler_path,
        loras=(),
        device=device,
    )
    pipeline.prompt_encoder = prompt_encoder

    try:
        tiling_config = TilingConfig.default()
        video_chunks_number = get_video_chunks_number(args.num_frames, tiling_config)
        LOGGER.info("Handing off into the LTX distilled pipeline.")
        video, audio = pipeline(
            prompt=args.prompt,
            seed=args.seed,
            height=args.height,
            width=args.width,
            num_frames=args.num_frames,
            frame_rate=args.frame_rate,
            images=args.images,
            tiling_config=tiling_config,
            enhance_prompt=args.enhance_prompt,
        )
        encode_video(
            video=video,
            fps=args.frame_rate,
            audio=audio,
            output_path=args.output_path,
            video_chunks_number=video_chunks_number,
        )
        LOGGER.info("Video written to %s", args.output_path)
        return 0
    except Exception as exc:
        LOGGER.exception("Standalone Comfy-style distilled experiment failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
