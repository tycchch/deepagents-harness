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
    source: str = "desktop"
    parent_thread_id: str | None = None
    forked_from_turn_id: str | None = None
    root_thread_id: str | None = None

    def to_info(self) -> ThreadInfo:
        return ThreadInfo(
            thread_id=self.thread_id,
            workspace=self.workspace,
            title=self.title,
            updated_at=self.updated_at,
            archived=self.archived,
            source=self.source or "desktop",
            parent_thread_id=self.parent_thread_id,
            forked_from_turn_id=self.forked_from_turn_id,
            root_thread_id=self.root_thread_id or self.thread_id,
        )


class ThreadStore:
    """thread_id 即日后 LangGraph configurable.thread_id。只持久化元数据。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._items: dict[str, ThreadRecord] = {}
        self._load()

    @property
    def path(self) -> Path | None:
        return self._path

    def start(self, workspace: str, *, source: str = "desktop") -> ThreadInfo:
        record = ThreadRecord(
            thread_id=str(uuid4()),
            workspace=normalize_workspace(workspace),
            updated_at=_now(),
            source=source or "desktop",
        )
        record.root_thread_id = record.thread_id
        self._items[record.thread_id] = record
        self._save()
        return record.to_info()

    def fork(
        self,
        thread_id: str,
        turn_id: str,
        workspace: str,
        *,
        child_id: str | None = None,
    ) -> ThreadInfo | None:
        parent = self._items.get(thread_id)
        if parent is None:
            return None
        child_id = child_id or str(uuid4())
        record = ThreadRecord(
            thread_id=child_id,
            workspace=normalize_workspace(workspace),
            title=f"{parent.title} (fork)" if parent.title else "Fork",
            updated_at=_now(),
            source=parent.source or "desktop",
            parent_thread_id=thread_id,
            forked_from_turn_id=turn_id,
            root_thread_id=parent.root_thread_id or parent.thread_id,
        )
        self._items[child_id] = record
        self._save()
        return record.to_info()

    def get(self, thread_id: str) -> ThreadInfo | None:
        record = self._items.get(thread_id)
        if record is None:
            return None
        return record.to_info()

    def resume(self, thread_id: str) -> ThreadInfo | None:
        return self.get(thread_id)

    def list(self, *, include_archived: bool = False, source: str | None = None) -> list[ThreadInfo]:
        items = [
            item.to_info()
            for item in self._items.values()
            if (include_archived or not item.archived)
            and (source is None or (item.source or "desktop") == source)
        ]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def latest_for_workspace(self, workspace: str, *, source: str | None = None) -> ThreadInfo | None:
        target = normalize_workspace(workspace)
        for item in self.list(source=source):
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
            # model_validate的作用是从任意 Python 对象（字典、模型实例、ORM 对象等）验证数据，并创建/返回一个模型实例。
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
