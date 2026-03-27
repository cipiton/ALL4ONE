from __future__ import annotations

import json
import os
from pathlib import Path

from .chat_state import ChatSessionState


def default_conversation_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "FakeAgent"
    return Path.home() / ".fake_agent"


class ConversationStore:
    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = (storage_dir or default_conversation_data_dir()).expanduser().resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "conversations.json"

    def load(self) -> tuple[list[ChatSessionState], str | None]:
        if not self.storage_path.exists():
            return [], None
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [], None

        conversations = [
            ChatSessionState.from_dict(item)
            for item in payload.get("conversations", [])
            if isinstance(item, dict)
        ]
        active_id = payload.get("active_conversation_id")
        active_value = str(active_id) if active_id else None
        return conversations, active_value

    def save(self, conversations: list[ChatSessionState], active_conversation_id: str | None) -> None:
        payload = {
            "active_conversation_id": active_conversation_id or "",
            "conversations": [conversation.to_dict() for conversation in conversations],
        }
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
