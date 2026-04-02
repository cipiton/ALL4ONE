from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_MODES = ("custom_voice", "voice_design", "voice_clone")
DEFAULT_MODELS = {
    "custom_voice": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "voice_design": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "voice_clone": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}


class RunnerError(Exception):
    """Base error for controlled runner failures."""


class DependencyError(RunnerError):
    """Raised when the local TTS environment is incomplete."""


class ValidationError(RunnerError):
    """Raised when CLI arguments do not form a valid request."""


class ModelAccessError(RunnerError):
    """Raised when a Qwen model cannot be loaded."""


@dataclass(frozen=True)
class RunnerConfig:
    text: str
    text_file_path: Path | None
    output_path: Path
    mode: str
    model_ref: str
    ref_audio: Path | None
    voice: str | None
    prompt_text: str | None
    language: str
    device: str
    dtype_name: str
    attn_implementation: str | None
    dry_run: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone Qwen TTS runner for the isolated TTS_qwen workspace."
    )
    text_input_group = parser.add_mutually_exclusive_group(required=True)
    text_input_group.add_argument("--text", help="Text to synthesize.")
    text_input_group.add_argument(
        "--text-file",
        help="Path to a UTF-8 text file to synthesize instead of --text.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Target audio file path, for example .\\outputs\\sample.wav.",
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="custom_voice",
        help="Generation mode.",
    )
    parser.add_argument(
        "--ref_audio",
        help="Reference audio path for voice_clone mode.",
    )
    parser.add_argument(
        "--voice",
        help="Speaker name for custom_voice mode, for example Ryan or Vivian.",
    )
    parser.add_argument(
        "--prompt_text",
        help="Mode-specific prompt text: style, voice design description, or ref transcript.",
    )
    parser.add_argument(
        "--model",
        help="Optional Hugging Face model id or local model directory override.",
    )
    parser.add_argument(
        "--language",
        default="Auto",
        help="Language hint passed to Qwen. Defaults to Auto.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help='Device target passed to model loading, for example "auto", "cpu", or "cuda:0".',
    )
    parser.add_argument(
        "--dtype",
        choices=("auto", "float32", "float16", "bfloat16"),
        default="auto",
        help="Torch dtype for model loading.",
    )
    parser.add_argument(
        "--attn_implementation",
        default="auto",
        help='Optional attention implementation. Use "auto" to omit it.',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate arguments and output path without loading the model.",
    )
    return parser


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"--text-file must be UTF-8 text: {path}") from exc


def validate_args(args: argparse.Namespace) -> RunnerConfig:
    raw_text = clean_optional_text(args.text)
    text_file_path = Path(args.text_file).expanduser() if args.text_file else None

    if text_file_path is not None:
        if not text_file_path.exists():
            raise ValidationError(f"Text file not found: {text_file_path}")
        if not text_file_path.is_file():
            raise ValidationError(f"Text file path must be a file: {text_file_path}")
        text = read_text_file(text_file_path).strip()
    else:
        text = (raw_text or "").strip()

    if not text:
        if text_file_path is not None:
            raise ValidationError(f"--text-file is empty: {text_file_path}")
        raise ValidationError("--text cannot be empty.")

    output_path = Path(args.output).expanduser()
    if output_path.exists() and output_path.is_dir():
        raise ValidationError("--output must be a file path, not an existing directory.")
    if output_path.suffix == "":
        raise ValidationError("--output must include an audio filename such as output.wav.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ref_audio = Path(args.ref_audio).expanduser() if args.ref_audio else None
    voice = clean_optional_text(args.voice)
    prompt_text = clean_optional_text(args.prompt_text)
    mode = args.mode

    if mode == "custom_voice":
        if not voice:
            raise ValidationError("--voice is required for custom_voice mode.")
        if ref_audio is not None:
            raise ValidationError("--ref_audio is only supported in voice_clone mode.")
    elif mode == "voice_design":
        if not prompt_text:
            raise ValidationError("--prompt_text is required for voice_design mode.")
        if voice is not None:
            raise ValidationError("--voice is not supported in voice_design mode.")
        if ref_audio is not None:
            raise ValidationError("--ref_audio is only supported in voice_clone mode.")
    elif mode == "voice_clone":
        if ref_audio is None:
            raise ValidationError("--ref_audio is required for voice_clone mode.")
        if not ref_audio.exists():
            raise ValidationError(f"Reference audio not found: {ref_audio}")
        if not ref_audio.is_file():
            raise ValidationError(f"Reference audio must be a file: {ref_audio}")
        if voice is not None:
            raise ValidationError("--voice is not supported in voice_clone mode.")
    else:
        raise ValidationError(f"Unsupported mode: {mode}")

    model_ref = clean_optional_text(args.model) or DEFAULT_MODELS[mode]
    model_path = Path(model_ref).expanduser()
    if model_path.exists():
        model_ref = str(model_path.resolve())

    attn_implementation = None
    if clean_optional_text(args.attn_implementation) not in (None, "auto"):
        attn_implementation = args.attn_implementation

    return RunnerConfig(
        text=text,
        text_file_path=text_file_path.resolve() if text_file_path else None,
        output_path=output_path.resolve(),
        mode=mode,
        model_ref=model_ref,
        ref_audio=ref_audio.resolve() if ref_audio else None,
        voice=voice,
        prompt_text=prompt_text,
        language=args.language,
        device=args.device,
        dtype_name=args.dtype,
        attn_implementation=attn_implementation,
        dry_run=bool(args.dry_run),
    )


class QwenTTSAdapter:
    """Keeps the Qwen-specific API calls isolated from CLI/request handling."""

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config
        self._torch = None
        self._soundfile = None
        self._model_cls = None

    def synthesize_to_file(self) -> Path:
        self._import_runtime()
        model = self._load_model()
        wavs, sample_rate = self._run_generation(model)
        audio = self._first_audio_item(wavs)
        self._soundfile.write(str(self.config.output_path), audio, sample_rate)
        return self.config.output_path

    def _import_runtime(self) -> None:
        try:
            import soundfile as soundfile  # type: ignore
            import torch  # type: ignore
            from qwen_tts import Qwen3TTSModel  # type: ignore
        except ModuleNotFoundError as exc:
            missing_name = exc.name or "unknown package"
            raise DependencyError(
                "Missing dependency "
                f"'{missing_name}'. Activate the TTS_qwen virtual environment and run "
                "`pip install -r requirements.txt`."
            ) from exc

        self._soundfile = soundfile
        self._torch = torch
        self._model_cls = Qwen3TTSModel

    def _load_model(self) -> Any:
        load_kwargs: dict[str, Any] = {
            "device_map": self.config.device,
            "dtype": self._resolve_dtype(),
        }
        if self.config.attn_implementation:
            load_kwargs["attn_implementation"] = self.config.attn_implementation

        try:
            return self._model_cls.from_pretrained(self.config.model_ref, **load_kwargs)
        except Exception as exc:  # pragma: no cover - depends on local runtime/model access
            raise ModelAccessError(
                "Could not load the Qwen model from "
                f"'{self.config.model_ref}'. Confirm the model id or local path, your "
                "network/auth access, and that the environment has enough runtime support."
            ) from exc

    def _resolve_dtype(self) -> Any:
        if self.config.dtype_name == "float32":
            return self._torch.float32
        if self.config.dtype_name == "float16":
            return self._torch.float16
        if self.config.dtype_name == "bfloat16":
            return self._torch.bfloat16

        cuda_available = bool(getattr(self._torch, "cuda", None)) and self._torch.cuda.is_available()
        return self._torch.bfloat16 if cuda_available else self._torch.float32

    def _run_generation(self, model: Any) -> tuple[Any, int]:
        # Keep the Qwen API touchpoints in one place so future service wrapping only needs
        # to reuse or replace this adapter layer if the upstream package changes.
        if self.config.mode == "custom_voice":
            return model.generate_custom_voice(
                text=self.config.text,
                language=self.config.language,
                speaker=self.config.voice,
                instruct=self.config.prompt_text,
            )

        if self.config.mode == "voice_design":
            return model.generate_voice_design(
                text=self.config.text,
                language=self.config.language,
                instruct=self.config.prompt_text,
            )

        if self.config.mode == "voice_clone":
            clone_kwargs: dict[str, Any] = {
                "text": self.config.text,
                "language": self.config.language,
                "ref_audio": str(self.config.ref_audio),
            }
            if self.config.prompt_text:
                clone_kwargs["ref_text"] = self.config.prompt_text
            else:
                clone_kwargs["x_vector_only_mode"] = True
            return model.generate_voice_clone(**clone_kwargs)

        raise ValidationError(f"Unsupported mode: {self.config.mode}")

    @staticmethod
    def _first_audio_item(wavs: Any) -> Any:
        if isinstance(wavs, (list, tuple)):
            if not wavs:
                raise RunnerError("The model returned no audio output.")
            return wavs[0]
        return wavs


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = validate_args(args)

    if config.dry_run:
        print(f"DRY RUN OK: mode={config.mode}")
        print(f"MODEL: {config.model_ref}")
        print(f"OUTPUT: {config.output_path}")
        if config.text_file_path:
            print(f"TEXT FILE: {config.text_file_path}")
        if config.ref_audio:
            print(f"REF AUDIO: {config.ref_audio}")
        if config.voice:
            print(f"VOICE: {config.voice}")
        if config.prompt_text:
            print("PROMPT TEXT: provided")
        else:
            print("PROMPT TEXT: not provided")
        return 0

    adapter = QwenTTSAdapter(config)
    output_path = adapter.synthesize_to_file()
    print(f"SUCCESS: audio written to {output_path}")
    return 0


def main() -> int:
    try:
        return run()
    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:  # pragma: no cover - safety net
        print("ERROR: unexpected failure while running Qwen TTS.", file=sys.stderr)
        print(f"DETAILS: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
