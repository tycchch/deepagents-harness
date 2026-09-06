from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from protocol.methods import ThreadInfo


class ThreadRecord(BaseModel):
    thread_id: str
    workspace: str
    title: str = ""
    updated_at: str = ""
    archived: bool = False

    def to_info(self) -> ThreadInfo:
        return ThreadInfo(
            thread_id=self.thread_id,
            workspace=self.workspace,
            title=self.title,
            updated_at=self.updated_at,
        )


class ThreadStore:
    """thread_id 即日后 LangGraph configurable.thread_id。只持久化元数据。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._items: dict[str, ThreadRecord] = {}
        self._load()

    def start(self, workspace: str) -> ThreadInfo:
        record = ThreadRecord(
            thread_id=str(uuid4()),
            workspace=workspace,
            updated_at=_now(),
        )
        self._items[record.thread_id] = record
        self._save()
        return record.to_info()

    def get(self, thread_id: str) -> ThreadInfo | None:
        record = self._items.get(thread_id)
        if record is None or record.archived:
            return None
        return record.to_info()

    def resume(self, thread_id: str) -> ThreadInfo | None:
        return self.get(thread_id)

    def list(self) -> list[ThreadInfo]:
        return [item.to_info() for item in self._items.values() if not item.archived]

    def archive(self, thread_id: str) -> bool:
        record = self._items.get(thread_id)
        if record is None:
            return False
        record.archived = True
        record.updated_at = _now()
        self._save()
        return True

    def touch(self, thread_id: str, title: str | None = None) -> None:
        record = self._items.get(thread_id)
        if record is None:
            return
        record.updated_at = _now()
        if title is not None:
            record.title = title
        self._save()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        for item in raw:
            record = ThreadRecord.model_validate(item)
            self._items[record.thread_id] = record

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in self._items.values()]
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
