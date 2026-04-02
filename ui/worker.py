from __future__ import annotations

import builtins
import io
import sys
import traceback
from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any

from engine import terminal_ui

from .backend_adapter import GuiBackend, GuiRunRequest


WorkerEvent = tuple[str, Any]


class WorkerCancelledError(Exception):
    pass


@dataclass(slots=True)
class WorkerPrompt:
    prompt: str
    prompt_kind: str = "text"
    choices: list[str] = field(default_factory=list)
    allow_blank: bool = False
    default_value: str = ""


class QueueStream(io.TextIOBase):
    def __init__(self, event_queue: Queue[WorkerEvent]) -> None:
        self._event_queue = event_queue
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        normalized = text.replace("\r\n", "\n")
        self._buffer += normalized
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._event_queue.put(("log", line + "\n"))
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._event_queue.put(("log", self._buffer))
            self._buffer = ""


class GuiWorker(Thread):
    def __init__(
        self,
        backend: GuiBackend,
        request: GuiRunRequest,
        event_queue: Queue[WorkerEvent],
    ) -> None:
        super().__init__(daemon=True)
        self._backend = backend
        self._request = request
        self._event_queue = event_queue
        self._input_queue: Queue[str] = Queue()
        self._cancel_requested = Event()

    def submit_input(self, value: str) -> None:
        self._input_queue.put(value)

    def request_cancel(self) -> None:
        self._cancel_requested.set()

    def run(self) -> None:
        stream = QueueStream(self._event_queue)
        self._event_queue.put(("started", None))
        try:
            with redirect_stdout(stream), redirect_stderr(stream), self._patch_prompt_bridge(), self._patch_cancel_trace():
                result = self._backend.run(self._request)
            stream.flush()
            self._event_queue.put(("result", result))
        except WorkerCancelledError:
            stream.flush()
            self._event_queue.put(("cancelled", None))
        except Exception as exc:  # noqa: BLE001
            stream.write(traceback.format_exc())
            stream.flush()
            self._event_queue.put(("error", str(exc)))
        finally:
            self._event_queue.put(("finished", None))

    @contextmanager
    def _patch_cancel_trace(self):
        previous = sys.gettrace()
        sys.settrace(self._trace_cancel)
        try:
            yield
        finally:
            sys.settrace(previous)

    @contextmanager
    def _patch_prompt_bridge(self):
        original_input = builtins.input
        originals = {
            "prompt_for_runtime_value": terminal_ui.prompt_for_runtime_value,
            "prompt_for_episode_selection": terminal_ui.prompt_for_episode_selection,
            "prompt_for_regeneration_instruction": terminal_ui.prompt_for_regeneration_instruction,
            "prompt_for_review_action": terminal_ui.prompt_for_review_action,
            "prompt_for_improvement_request": terminal_ui.prompt_for_improvement_request,
            "prompt_for_restart_request": terminal_ui.prompt_for_restart_request,
            "ask_yes_no": terminal_ui.ask_yes_no,
            "show_step_output_preview": terminal_ui.show_step_output_preview,
            "print_full_output": terminal_ui.print_full_output,
        }

        builtins.input = self._fallback_input  # type: ignore[assignment]
        terminal_ui.prompt_for_runtime_value = self._prompt_for_runtime_value  # type: ignore[assignment]
        terminal_ui.prompt_for_episode_selection = self._prompt_for_episode_selection  # type: ignore[assignment]
        terminal_ui.prompt_for_regeneration_instruction = self._prompt_for_regeneration_instruction  # type: ignore[assignment]
        terminal_ui.prompt_for_review_action = self._prompt_for_review_action  # type: ignore[assignment]
        terminal_ui.prompt_for_improvement_request = self._prompt_for_improvement_request  # type: ignore[assignment]
        terminal_ui.prompt_for_restart_request = self._prompt_for_restart_request  # type: ignore[assignment]
        terminal_ui.ask_yes_no = self._ask_yes_no  # type: ignore[assignment]
        terminal_ui.show_step_output_preview = self._show_step_output_preview  # type: ignore[assignment]
        terminal_ui.print_full_output = self._print_full_output  # type: ignore[assignment]
        try:
            yield
        finally:
            builtins.input = original_input  # type: ignore[assignment]
            for name, func in originals.items():
                setattr(terminal_ui, name, func)

    def _emit_prompt(self, request: WorkerPrompt) -> str:
        self._event_queue.put(("awaiting_input", request))
        while True:
            self._raise_if_cancelled()
            try:
                reply = self._input_queue.get(timeout=0.1)
                break
            except Empty:
                continue
        self._event_queue.put(("input_resumed", None))
        return reply

    def _trace_cancel(self, frame, event, arg):
        self._raise_if_cancelled()
        return self._trace_cancel

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested.is_set():
            raise WorkerCancelledError("Cancelled by user.")

    def _emit_preview(self, title: str, text: str, *, kind: str) -> None:
        self._event_queue.put(
            (
                "preview",
                {
                    "title": title.strip(),
                    "text": text.rstrip(),
                    "full_text": text.rstrip(),
                    "kind": kind,
                },
            )
        )

    def _fallback_input(self, prompt: str = "") -> str:
        prompt_text = (prompt or "").strip() or "Input required:"
        return self._emit_prompt(WorkerPrompt(prompt=prompt_text))

    def _show_step_output_preview(
        self,
        step_title: str,
        text: str,
        *,
        max_lines: int = 18,
        max_chars: int = 1400,
    ) -> None:
        preview_text = text[:max_chars]
        preview_lines = preview_text.splitlines()
        truncated_lines = len(preview_lines) > max_lines
        if truncated_lines:
            preview_lines = preview_lines[:max_lines]
        rendered = "\n".join(preview_lines).strip() or "(empty output)"
        if truncated_lines or len(text) > len(preview_text):
            rendered = f"{rendered}\n..."

        self._event_queue.put(
            (
                "preview",
                {
                    "title": step_title.strip(),
                    "text": rendered,
                    "full_text": text.rstrip() or "(empty output)",
                    "kind": "preview",
                },
            )
        )

        print()
        print(f"Preview: {step_title}")
        print("-" * 60)
        print(rendered)
        print("-" * 60)

    def _print_full_output(self, step_title: str, text: str) -> None:
        rendered = text.rstrip() or "(empty output)"
        self._emit_preview(step_title, rendered, kind="full_output")

        print()
        print(f"Full output: {step_title}")
        print("=" * 60)
        print(rendered)
        print("=" * 60)

    def _prompt_for_runtime_value(self, definition, current_value: Any = None) -> Any:
        error_prefix = ""
        while True:
            lines: list[str] = []
            if error_prefix:
                lines.append(error_prefix)
            if getattr(definition, "help_text", ""):
                lines.append(str(definition.help_text).strip())

            if getattr(definition, "field_type", "") == "choice":
                lines.append(str(definition.prompt).strip())
                choices = list(getattr(definition, "choices", []) or [])
                for index, choice in enumerate(choices, start=1):
                    suffix = " (current)" if current_value == choice else ""
                    lines.append(f"{index}. {choice}{suffix}")
                raw_value = self._emit_prompt(
                    WorkerPrompt(
                        prompt="\n".join(item for item in lines if item).strip(),
                        prompt_kind="choice",
                        choices=choices,
                        allow_blank=(current_value is not None or getattr(definition, "default", None) is not None or not bool(getattr(definition, "required", True))),
                        default_value=str(current_value if current_value is not None else getattr(definition, "default", "") or ""),
                    )
                ).strip()
            else:
                default_suffix = ""
                if current_value is not None:
                    default_suffix = f" [{current_value}]"
                elif getattr(definition, "default", None) is not None:
                    default_suffix = f" [{definition.default}]"
                lines.append(f"{definition.prompt}{default_suffix}:")
                raw_value = self._emit_prompt(
                    WorkerPrompt(
                        prompt="\n".join(item for item in lines if item).strip(),
                        prompt_kind=str(getattr(definition, "field_type", "text") or "text"),
                        allow_blank=(current_value is not None or getattr(definition, "default", None) is not None or not bool(getattr(definition, "required", True))),
                        default_value=str(current_value if current_value is not None else getattr(definition, "default", "") or ""),
                    )
                ).strip()

            if not raw_value:
                if current_value is not None:
                    return current_value
                if getattr(definition, "default", None) is not None:
                    return definition.default
                if not bool(getattr(definition, "required", True)):
                    return None
                error_prefix = "This value is required."
                continue

            try:
                return terminal_ui._parse_runtime_value(definition, raw_value)
            except ValueError as exc:
                error_prefix = str(exc)

    def _prompt_for_episode_selection(
        self,
        total_episodes: int,
        *,
        mode: str,
        current_value: str | None = None,
    ) -> str:
        action = "generated" if mode == "generate" else "regenerated"
        lines = [
            f"There are {total_episodes} episodes in this adaptation plan.",
            f"Which episodes should be {action}?",
        ]
        if mode == "generate":
            lines.append("Examples: blank = all, all, 1-10, 11-20, 60, 15,18,22")
        else:
            lines.append("Examples: 15, 15-16, 02-05, 15,18,22")
        default_value = current_value or ("all" if mode == "generate" else "")
        return self._emit_prompt(
            WorkerPrompt(
                prompt="\n".join(lines),
                prompt_kind="text",
                allow_blank=True,
                default_value=default_value,
            )
        ).strip()

    def _prompt_for_regeneration_instruction(self, current_value: str | None = None) -> str:
        lines = [
            "Optional regeneration instruction.",
            "Examples: more detailed, improve pacing, stronger hook, better dialogue, preserve current structure",
        ]
        return self._emit_prompt(
            WorkerPrompt(
                prompt="\n".join(lines),
                prompt_kind="text",
                allow_blank=True,
                default_value=current_value or "",
            )
        ).strip()

    def _prompt_for_review_action(self) -> str:
        while True:
            reply = self._emit_prompt(
                WorkerPrompt(
                    prompt="Choose: [A]ccept, [I]mprove, [R]estart, [V]iew full, [C]ancel:",
                    prompt_kind="choice",
                    choices=["accept", "improve", "restart", "view_full", "cancel"],
                    allow_blank=True,
                    default_value="accept",
                )
            ).strip().lower()
            if reply in {"", "a", "accept"}:
                return "accept"
            if reply in {"i", "improve"}:
                return "improve"
            if reply in {"r", "restart"}:
                return "restart"
            if reply in {"v", "view", "full", "view_full"}:
                return "view_full"
            if reply in {"c", "cancel", "q", "quit"}:
                return "cancel"

    def _prompt_for_improvement_request(self) -> str:
        return self._emit_prompt(
            WorkerPrompt(
                prompt="Improvement instructions:",
                prompt_kind="text",
                allow_blank=False,
            )
        ).strip()

    def _prompt_for_restart_request(self) -> str:
        return self._emit_prompt(
            WorkerPrompt(
                prompt="Restart instructions (optional):",
                prompt_kind="text",
                allow_blank=True,
            )
        ).strip()

    def _ask_yes_no(self, prompt: str, default: bool = False) -> bool:
        while True:
            reply = self._emit_prompt(
                WorkerPrompt(
                    prompt=prompt.strip(),
                    prompt_kind="bool",
                    choices=["yes", "no"],
                    allow_blank=True,
                    default_value="yes" if default else "no",
                )
            ).strip().lower()
            if not reply:
                return default
            if reply in {"y", "yes", "true", "1"}:
                return True
            if reply in {"n", "no", "false", "0"}:
                return False
