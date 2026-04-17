from __future__ import annotations

import gc
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import torch
from transformers import (
    AutoImageProcessor,
    AutoTokenizer,
    Gemma3ForConditionalGeneration,
    Gemma3Processor,
)


LOGGER = logging.getLogger("comfy_gemma_bridge")

REPO_ROOT = Path(__file__).resolve().parents[1]
LTX_ROOT = REPO_ROOT / "LTX-2"
for relative_path in ("packages/ltx-core/src", "packages/ltx-pipelines/src"):
    import_path = str((LTX_ROOT / relative_path).resolve())
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from ltx_core.loader.registry import DummyRegistry  # noqa: E402
from ltx_core.loader.single_gpu_model_builder import SingleGPUModelBuilder as Builder  # noqa: E402
from ltx_core.text_encoders.gemma import (  # noqa: E402
    EMBEDDINGS_PROCESSOR_KEY_OPS,
    EmbeddingsProcessorConfigurator,
)
from ltx_core.text_encoders.gemma.embeddings_processor import EmbeddingsProcessorOutput  # noqa: E402


DEFAULT_DISTILLED_CHECKPOINT = (
    r"\\Suntec\Metis\Comfy_Metis\models\checkpoints\ltx-2.3-22b-distilled-fp8.safetensors"
)
DEFAULT_GEMMA_ROOT = (
    r"\\Suntec\Metis\Comfy_Metis\models\text_encoders\gemma-3-12b-it-qat-q4_0-unquantized"
)
DEFAULT_SPATIAL_UPSAMPLER = (
    r"\\Suntec\Metis\Comfy_Metis\models\latent_upscale_models\ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors"
)
DEFAULT_IMAGE = (
    r"C:\Users\CP\Documents\WORKSPACES\ONE4ALL\OUTPUTSSAVED\2222\generated_keyscenes\keyscenes\ep02_s05.png"
)
DEFAULT_OUTPUT = r"C:\Users\CP\Documents\WORKSPACES\ONE4ALL\outputs\ltx_test_distilled_low.mp4"
DEFAULT_PROMPT = "The woman lowers her head, then slowly looks up. The work light flickers. The camera slowly pushes in."


def _safe_cleanup_memory() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


@contextmanager
def safe_model_context(model: torch.nn.Module) -> Iterator[torch.nn.Module]:
    try:
        yield model
    finally:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        try:
            model.to("meta")
        except Exception:
            LOGGER.debug("Could not move model to meta during cleanup.", exc_info=True)
        _safe_cleanup_memory()


def install_cpu_safe_gpu_model_patch() -> None:
    if torch.cuda.is_available():
        return

    LOGGER.warning("CUDA is unavailable. Installing a CPU-safe gpu_model shim for this experiment.")

    from ltx_pipelines.utils import blocks as blocks_module  # noqa: WPS433
    from ltx_pipelines.utils import gpu_model as gpu_model_module  # noqa: WPS433

    gpu_model_module.gpu_model = safe_model_context
    blocks_module.gpu_model = safe_model_context


class ComfyStyleGemmaTokenizer:
    def __init__(self, gemma_root: str | Path, max_length: int = 1024, pad_multiple: int = 128):
        self.gemma_root = str(Path(gemma_root).expanduser())
        self.max_length = max_length
        self.pad_multiple = pad_multiple
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.gemma_root,
            local_files_only=True,
            model_max_length=max_length,
        )
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def encode(self, prompt: str) -> tuple[torch.Tensor, torch.Tensor]:
        encoded = self.tokenizer(
            prompt.strip(),
            padding=True,
            max_length=self.max_length,
            truncation=True,
            return_tensors="pt",
        )
        sequence_length = encoded.input_ids.shape[1]
        padded_length = ((sequence_length + self.pad_multiple - 1) // self.pad_multiple) * self.pad_multiple
        pad_length = min(max(padded_length - sequence_length, 0), self.max_length - sequence_length)
        if pad_length > 0:
            encoded = self.tokenizer.pad(
                encoded,
                padding="max_length",
                max_length=sequence_length + pad_length,
                return_tensors="pt",
            )
        return encoded.input_ids, encoded.attention_mask


class ComfyStyleGemmaPromptEncoder:
    def __init__(
        self,
        *,
        checkpoint_path: str,
        gemma_root: str,
        dtype: torch.dtype,
        device: torch.device,
        max_length: int = 1024,
    ) -> None:
        self.checkpoint_path = str(Path(checkpoint_path).expanduser())
        self.gemma_root = str(Path(gemma_root).expanduser())
        self.dtype = dtype
        self.device = device
        self.max_length = max_length
        self._tokenizer_wrapper: ComfyStyleGemmaTokenizer | None = None
        self._processor: Gemma3Processor | None = None
        self._embeddings_builder = Builder(
            model_path=self.checkpoint_path,
            model_class_configurator=EmbeddingsProcessorConfigurator,
            model_sd_ops=EMBEDDINGS_PROCESSOR_KEY_OPS,
            registry=DummyRegistry(),
        )

    def _load_tokenizer(self) -> ComfyStyleGemmaTokenizer:
        if self._tokenizer_wrapper is None:
            LOGGER.info("Loading Gemma tokenizer from %s", self.gemma_root)
            self._tokenizer_wrapper = ComfyStyleGemmaTokenizer(self.gemma_root, max_length=self.max_length)
            LOGGER.info(
                "Gemma tokenizer loaded. max_length=%s pad_multiple=%s",
                self.max_length,
                self._tokenizer_wrapper.pad_multiple,
            )
        return self._tokenizer_wrapper

    def _load_processor_optional(self) -> Gemma3Processor | None:
        if self._processor is not None:
            return self._processor

        try:
            LOGGER.info("Attempting Gemma processor load from %s", self.gemma_root)
            image_processor = AutoImageProcessor.from_pretrained(
                self.gemma_root,
                local_files_only=True,
            )
            tokenizer = self._load_tokenizer().tokenizer
            self._processor = Gemma3Processor(image_processor=image_processor, tokenizer=tokenizer)
            LOGGER.info("Gemma processor loaded successfully.")
        except Exception as exc:
            LOGGER.warning("Gemma processor load skipped: %s", exc)
            self._processor = None
        return self._processor

    def _load_model(self) -> Gemma3ForConditionalGeneration:
        LOGGER.info("Loading Gemma model from %s", self.gemma_root)
        model = Gemma3ForConditionalGeneration.from_pretrained(
            self.gemma_root,
            local_files_only=True,
            torch_dtype=self.dtype,
            low_cpu_mem_usage=True,
        )
        model = model.to(self.device).eval()
        LOGGER.info("Gemma model loaded successfully on %s with dtype=%s", self.device, self.dtype)
        return model

    def _encode_prompt_with_model(
        self,
        model: Gemma3ForConditionalGeneration,
        prompt: str,
    ) -> tuple[tuple[torch.Tensor, ...], torch.Tensor]:
        tokenizer_wrapper = self._load_tokenizer()
        input_ids, attention_mask = tokenizer_wrapper.encode(prompt)
        input_ids = input_ids.to(model.device)
        attention_mask = attention_mask.to(model.device)

        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            use_cache=False,
        )
        hidden_states = outputs.hidden_states
        if hidden_states is None:
            raise RuntimeError("Gemma model did not return hidden_states.")
        LOGGER.info(
            "Prompt encoding success. hidden_layers=%s seq_len=%s device=%s",
            len(hidden_states),
            attention_mask.shape[-1],
            model.device,
        )
        return hidden_states, attention_mask

    def _process_hidden_states(
        self,
        raw_outputs: list[tuple[tuple[torch.Tensor, ...], torch.Tensor]],
    ) -> list[EmbeddingsProcessorOutput]:
        embeddings_processor = self._embeddings_builder.build(device=self.device, dtype=self.dtype).to(self.device).eval()
        with safe_model_context(embeddings_processor):
            processed_outputs = [embeddings_processor.process_hidden_states(hs, mask) for hs, mask in raw_outputs]

        for index, output in enumerate(processed_outputs):
            LOGGER.info(
                "Embedding %s: video_shape=%s video_dtype=%s video_device=%s mask_shape=%s",
                index,
                tuple(output.video_encoding.shape),
                output.video_encoding.dtype,
                output.video_encoding.device,
                tuple(output.attention_mask.shape),
            )
            if output.audio_encoding is not None:
                LOGGER.info(
                    "Embedding %s audio_shape=%s audio_dtype=%s audio_device=%s",
                    index,
                    tuple(output.audio_encoding.shape),
                    output.audio_encoding.dtype,
                    output.audio_encoding.device,
                )
        return processed_outputs

    def __call__(
        self,
        prompts: list[str],
        *,
        enhance_first_prompt: bool = False,
        enhance_prompt_image: str | None = None,
        enhance_prompt_seed: int = 42,
        streaming_prefetch_count: int | None = None,
    ) -> list[EmbeddingsProcessorOutput]:
        del enhance_prompt_image, enhance_prompt_seed, streaming_prefetch_count

        self._load_processor_optional()
        if enhance_first_prompt:
            raise RuntimeError(
                "The Comfy-style standalone bridge does not implement prompt enhancement yet. "
                "Run without --enhance-prompt."
            )

        model = self._load_model()
        try:
            with safe_model_context(model):
                raw_outputs = [self._encode_prompt_with_model(model, prompt) for prompt in prompts]
        finally:
            del model

        return self._process_hidden_states(raw_outputs)

    def encode_only(self, prompt: str) -> EmbeddingsProcessorOutput:
        return self([prompt])[0]
