from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from protocol.methods import ThreadInfo


def normalize_workspace(workspace: str) -> str:
    return str(Path(workspace).expanduser().resolve())


class ThreadRecord(BaseModel):
    thread_id: str
    workspace: str
    title: str = ""
    updated_at: str = ""
    archived: bool = False
    title_locked: bool = False

    def to_info(self) -> ThreadInfo:
        return ThreadInfo(
            thread_id=self.thread_id,
            workspace=self.workspace,
            title=self.title,
            updated_at=self.updated_at,
            archived=self.archived,
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
            workspace=normalize_workspace(workspace),
            updated_at=_now(),
        )
        self._items[record.thread_id] = record
        self._save()
        return record.to_info()

    def get(self, thread_id: str) -> ThreadInfo | None:
        record = self._items.get(thread_id)
        if record is None:
            return None
        return record.to_info()

    def resume(self, thread_id: str) -> ThreadInfo | None:
        return self.get(thread_id)

    def list(self, *, include_archived: bool = False) -> list[ThreadInfo]:
        items = [
            item.to_info()
            for item in self._items.values()
            if include_archived or not item.archived
        ]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def latest_for_workspace(self, workspace: str) -> ThreadInfo | None:
        target = normalize_workspace(workspace)
        for item in self.list():
            try:
                if normalize_workspace(item.workspace) == target:
                    return item
            except OSError:
                if item.workspace == workspace:
                    return item
        return None

    def delete(self, thread_id: str) -> bool:
        if self._items.pop(thread_id, None) is None:
            return False
        self._save()
        return True

    def archive(self, thread_id: str) -> bool:
        return self._set_archived(thread_id, True)

    def unarchive(self, thread_id: str) -> bool:
        return self._set_archived(thread_id, False)

    def _set_archived(self, thread_id: str, archived: bool) -> bool:
        record = self._items.get(thread_id)
        if record is None:
            return False
        record.archived = archived
        record.updated_at = _now()
        self._save()
        return True

    def set_workspace(self, thread_id: str, workspace: str) -> ThreadInfo | None:
        record = self._items.get(thread_id)
        if record is None:
            return None
        record.workspace = normalize_workspace(workspace)
        record.updated_at = _now()
        self._save()
        return record.to_info()

    def rename(self, thread_id: str, title: str) -> ThreadInfo | None:
        record = self._items.get(thread_id)
        if record is None:
            return None
        record.title = title.strip()
        record.title_locked = bool(record.title)
        self._save()
        return record.to_info()

    def touch(self, thread_id: str, title: str | None = None) -> None:
        record = self._items.get(thread_id)
        if record is None:
            return
        record.updated_at = _now()
        # Auto title comes from the first message; a manual rename wins forever.
        if title is not None and not record.title_locked and not record.title:
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
