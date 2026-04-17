from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


DEFAULT_MODEL_IDS = {
    "asset": "black-forest-labs/FLUX.2-klein-9B",
    "keyscene": "black-forest-labs/FLUX.2-klein-4B",
}
DEFAULT_STEPS = {
    "asset": 4,
    "keyscene": 4,
}
DEFAULT_GUIDANCE = 1.0
DEFAULT_SIZES = {
    "character": (512, 768),
    "scene": (768, 512),
    "environment": (768, 512),
    "prop": (512, 512),
    "vehicle": (512, 512),
    "wardrobe": (512, 512),
    "state_variant": (512, 512),
    "keyscene": (864, 1080),
}


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    backend: str
    mode: str
    model_id: str
    steps: int
    guidance_scale: float
    width: int
    height: int
    seed: int
    flux_python: Path | None = None
    flux_script: Path | None = None


@dataclass(frozen=True, slots=True)
class BatchGenerationJob:
    prompt: str
    output_path: Path
    config: GenerationConfig
    references: tuple[Path, ...] = ()
    job_id: str | None = None


class FluxImageGenerator:
    def __init__(self, backend: str = "diffusers") -> None:
        self.backend = normalize_backend_name(backend)
        self.repo_root = Path(__file__).resolve().parents[3]
        flux_root = Path(os.environ.get("ONE4ALL_FLUX_REPO") or (self.repo_root / "FLUX")).expanduser().resolve()
        self.default_flux_python = Path(
            os.environ.get("ONE4ALL_FLUX_PYTHON") or (flux_root / ".venv" / "Scripts" / "python.exe")
        ).expanduser().resolve()
        self.default_flux_script = Path(
            os.environ.get("ONE4ALL_FLUX_KLEIN_SCRIPT") or (flux_root / "klein.py")
        ).expanduser().resolve()

    def generate(
        self,
        *,
        prompt: str,
        output_path: Path,
        config: GenerationConfig,
        references: list[Path] | None = None,
        log_output: bool = True,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.backend == "mock":
            generate_mock_image(
                prompt=prompt,
                output_path=output_path,
                width=config.width,
                height=config.height,
                label=f"{config.mode}:{config.model_id.split('/')[-1]}",
            )
            return
        generate_with_klein_cli(
            prompt=prompt,
            output_path=output_path,
            config=config,
            references=references or [],
            default_flux_python=self.default_flux_python,
            default_flux_script=self.default_flux_script,
            log_output=log_output,
        )

    def generate_batch(self, jobs: list[BatchGenerationJob]) -> None:
        if not jobs:
            return
        if self.backend == "mock":
            for job in jobs:
                generate_mock_image(
                    prompt=job.prompt,
                    output_path=job.output_path,
                    width=job.config.width,
                    height=job.config.height,
                    label=f"{job.config.mode}:{job.config.model_id.split('/')[-1]}",
                )
            return
        generate_batch_with_klein_cli(
            jobs=jobs,
            default_flux_python=self.default_flux_python,
            default_flux_script=self.default_flux_script,
        )


def generate_with_klein_cli(
    *,
    prompt: str,
    output_path: Path,
    config: GenerationConfig,
    references: list[Path],
    default_flux_python: Path,
    default_flux_script: Path,
    log_output: bool = True,
) -> None:
    flux_python = (config.flux_python or default_flux_python).resolve()
    flux_script = (config.flux_script or default_flux_script).resolve()

    if not flux_python.exists():
        raise FileNotFoundError(
            f"FLUX Python executable does not exist: {flux_python}. "
            "Set ONE4ALL_FLUX_PYTHON if the venv lives elsewhere."
        )
    if not flux_script.exists():
        raise FileNotFoundError(
            f"FLUX klein.py does not exist: {flux_script}. "
            "Set ONE4ALL_FLUX_KLEIN_SCRIPT if the script lives elsewhere."
        )

    command = [
        str(flux_python),
        str(flux_script),
        "--output",
        str(output_path),
        "--model",
        config.model_id,
        "--width",
        str(config.width),
        "--height",
        str(config.height),
        "--steps",
        str(config.steps),
        "--guidance",
        str(config.guidance_scale),
        "--seed",
        str(config.seed),
        "--prompt",
        prompt,
    ]

    if len(references) > 0:
        command.extend(["--scene", str(references[0])])
    if len(references) > 1:
        command.extend(["--character", str(references[1])])
    if len(references) > 2:
        command.extend(["--prop", str(references[2])])

    completed = subprocess.run(
        command,
        cwd=str(flux_script.parent),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if log_output and completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"FLUX klein.py failed with exit code {completed.returncode}."
            + (f"\n{detail}" if detail else "")
        )
    if not output_path.exists():
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"FLUX klein.py reported success but did not create an output image: {output_path}"
            + (f"\n{detail}" if detail else "")
        )


def generate_batch_with_klein_cli(
    *,
    jobs: list[BatchGenerationJob],
    default_flux_python: Path,
    default_flux_script: Path,
) -> None:
    first_config = jobs[0].config
    flux_python = (first_config.flux_python or default_flux_python).resolve()
    flux_script = (first_config.flux_script or default_flux_script).resolve()

    if not flux_python.exists():
        raise FileNotFoundError(
            f"FLUX Python executable does not exist: {flux_python}. "
            "Set ONE4ALL_FLUX_PYTHON if the venv lives elsewhere."
        )
    if not flux_script.exists():
        raise FileNotFoundError(
            f"FLUX klein.py does not exist: {flux_script}. "
            "Set ONE4ALL_FLUX_KLEIN_SCRIPT if the script lives elsewhere."
        )

    for job in jobs:
        job.output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "jobs": [
            {
                "job_id": job.job_id,
                "output": str(job.output_path),
                "model": job.config.model_id,
                "width": job.config.width,
                "height": job.config.height,
                "steps": job.config.steps,
                "guidance": job.config.guidance_scale,
                "seed": job.config.seed,
                "prompt": job.prompt,
                "scene": str(job.references[0]) if len(job.references) > 0 else None,
                "character": str(job.references[1]) if len(job.references) > 1 else None,
                "prop": str(job.references[2]) if len(job.references) > 2 else None,
            }
            for job in jobs
        ]
    }
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        delete=False,
        dir=str(jobs[0].output_path.parent),
    )
    batch_file = Path(handle.name)
    try:
        with handle:
            handle.write(json_dumps(payload))

        command = [
            str(flux_python),
            str(flux_script),
            "--batch-file",
            str(batch_file),
        ]
        completed = subprocess.run(
            command,
            cwd=str(flux_script.parent),
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.stdout.strip():
            print(completed.stdout.strip())
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"FLUX klein.py batch mode failed with exit code {completed.returncode}."
                + (f"\n{detail}" if detail else "")
            )
        missing = [str(job.output_path) for job in jobs if not job.output_path.exists()]
        if missing:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                "FLUX klein.py batch mode reported success but did not create all output images:\n"
                + "\n".join(missing)
                + (f"\n{detail}" if detail else "")
            )
    finally:
        try:
            batch_file.unlink(missing_ok=True)
        except OSError:
            pass


def generate_mock_image(*, prompt: str, output_path: Path, width: int, height: int, label: str) -> None:
    image = Image.new("RGB", (width, height), color=(241, 236, 222))
    draw = ImageDraw.Draw(image)
    border_color = (44, 57, 79)
    draw.rectangle((12, 12, width - 12, height - 12), outline=border_color, width=4)
    wrapped = textwrap.fill(prompt[:260], width=42)
    body = f"{label}\n\n{wrapped}"
    draw.multiline_text((24, 24), body, fill=(32, 32, 32), spacing=6)
    image.save(output_path)


def build_generation_config(
    *,
    backend: str,
    mode: str,
    model_id: str | None,
    steps: int | None,
    guidance_scale: float | None,
    width: int | None,
    height: int | None,
    seed: int,
    asset_type: str | None = None,
) -> GenerationConfig:
    resolved_mode = "keyscene" if mode == "keyscene" else "asset"
    default_size_key = "keyscene" if resolved_mode == "keyscene" else (asset_type or "scene")
    default_width, default_height = DEFAULT_SIZES[default_size_key]
    return GenerationConfig(
        backend=normalize_backend_name(backend),
        mode=resolved_mode,
        model_id=model_id or DEFAULT_MODEL_IDS[resolved_mode],
        steps=steps if steps is not None else DEFAULT_STEPS[resolved_mode],
        guidance_scale=guidance_scale if guidance_scale is not None else DEFAULT_GUIDANCE,
        width=width or default_width,
        height=height or default_height,
        seed=seed,
    )


def normalize_backend_name(value: str) -> str:
    text = str(value or "klein_cli").strip().casefold()
    if text in {"mock", "test"}:
        return "mock"
    return "klein_cli"


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
