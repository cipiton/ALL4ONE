from __future__ import annotations

import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from queue import Queue
from threading import Thread
from typing import Any

from .backend_adapter import GuiBackend, GuiRunRequest


WorkerEvent = tuple[str, Any]


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

    def run(self) -> None:
        stream = QueueStream(self._event_queue)
        self._event_queue.put(("started", None))
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                result = self._backend.run(self._request)
            stream.flush()
            self._event_queue.put(("result", result))
        except Exception as exc:  # noqa: BLE001
            stream.write(traceback.format_exc())
            stream.flush()
            self._event_queue.put(("error", str(exc)))
        finally:
            self._event_queue.put(("finished", None))
