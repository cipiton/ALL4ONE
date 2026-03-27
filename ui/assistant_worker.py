from __future__ import annotations

import traceback
from queue import Queue
from threading import Thread
from typing import Any

from .llm_client import AssistantRequest, generate_assistant_reply


AssistantEvent = tuple[str, Any]


class AssistantWorker(Thread):
    def __init__(
        self,
        request: AssistantRequest,
        conversation_id: str,
        event_queue: Queue[AssistantEvent],
    ) -> None:
        super().__init__(daemon=True)
        self._request = request
        self._conversation_id = conversation_id
        self._event_queue = event_queue

    def run(self) -> None:
        self._event_queue.put(("assistant_started", self._conversation_id))
        try:
            reply = generate_assistant_reply(self._request)
            self._event_queue.put(("assistant_result", (self._conversation_id, reply)))
        except Exception as exc:  # noqa: BLE001
            self._event_queue.put(("assistant_error", (self._conversation_id, str(exc), traceback.format_exc())))
        finally:
            self._event_queue.put(("assistant_finished", self._conversation_id))
