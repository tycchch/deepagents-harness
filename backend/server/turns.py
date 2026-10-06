from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class TurnRecord:
    """A durable turn boundary used as the future fork target."""

    turn_id: str
    thread_id: str
    status: str
    checkpoint_id: str | None
    workspace_manifest_id: str | None
    started_at: str
    completed_at: str | None


class TurnStore:
    """Small SQLite index from a completed turn to its LangGraph checkpoint.

    LangGraph owns checkpoint serialization. This store only records which
    checkpoint is the stable end state for each user-visible turn.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            database = str(self._path)
        else:
            database = ":memory:"
        self._conn = sqlite3.connect(database)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    @property
    def path(self) -> Path | None:
        return self._path

    def start(self, thread_id: str) -> TurnRecord:
        record = TurnRecord(
            turn_id=str(uuid4()),
            thread_id=thread_id,
            status="running",
            checkpoint_id=None,
            workspace_manifest_id=None,
            started_at=_now(),
            completed_at=None,
        )
        self._conn.execute(
            """
            INSERT INTO turns (turn_id, thread_id, status, checkpoint_id, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.turn_id,
                record.thread_id,
                record.status,
                record.checkpoint_id,
                record.started_at,
                record.completed_at,
            ),
        )
        self._conn.commit()
        return record

    def finish(
        self,
        turn_id: str,
        *,
        status: str,
        checkpoint_id: str | None = None,
        workspace_manifest_id: str | None = None,
    ) -> TurnRecord:
        completed_at = _now()
        cursor = self._conn.execute(
            """
            UPDATE turns
            SET status = ?, checkpoint_id = ?, workspace_manifest_id = ?, completed_at = ?
            WHERE turn_id = ?
            """,
            (status, checkpoint_id, workspace_manifest_id, completed_at, turn_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(turn_id)
        self._conn.commit()
        record = self.get(turn_id)
        if record is None:
            raise RuntimeError(f"turn disappeared after update: {turn_id}")
        return record

    def get(self, turn_id: str) -> TurnRecord | None:
        row = self._conn.execute(
            """
            SELECT turn_id, thread_id, status, checkpoint_id, workspace_manifest_id,
                   started_at, completed_at
            FROM turns WHERE turn_id = ?
            """,
            (turn_id,),
        ).fetchone()
        return _record(row) if row is not None else None

    def list_for_thread(self, thread_id: str) -> list[TurnRecord]:
        rows = self._conn.execute(
            """
            SELECT turn_id, thread_id, status, checkpoint_id, workspace_manifest_id,
                   started_at, completed_at
            FROM turns WHERE thread_id = ? ORDER BY started_at ASC, rowid ASC
            """,
            (thread_id,),
        ).fetchall()
        return [_record(row) for row in rows]

    def delete_thread(self, thread_id: str) -> None:
        self._conn.execute("DELETE FROM turns WHERE thread_id = ?", (thread_id,))
        self._conn.commit()

    def _setup(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                turn_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                status TEXT NOT NULL,
                checkpoint_id TEXT,
                workspace_manifest_id TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        columns = {
            str(row[1]) for row in self._conn.execute("PRAGMA table_info(turns)").fetchall()
        }
        if "workspace_manifest_id" not in columns:
            self._conn.execute("ALTER TABLE turns ADD COLUMN workspace_manifest_id TEXT")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS turns_thread_started ON turns(thread_id, started_at)"
        )
        self._conn.commit()


def _record(row: sqlite3.Row) -> TurnRecord:
    return TurnRecord(
        turn_id=str(row["turn_id"]),
        thread_id=str(row["thread_id"]),
        status=str(row["status"]),
        checkpoint_id=str(row["checkpoint_id"]) if row["checkpoint_id"] is not None else None,
        workspace_manifest_id=(
            str(row["workspace_manifest_id"])
            if row["workspace_manifest_id"] is not None
            else None
        ),
        started_at=str(row["started_at"]),
        completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
