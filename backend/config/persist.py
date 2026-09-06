from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from config.schema import HarnessConfig

# from_conn_string() is a context manager and would close the DB. Keep conns for process life.
_HELD: list[object] = []


def _expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _sqlite_import_error(kind: str) -> str:
    return (
        f"persist.{kind}=sqlite needs langgraph-checkpoint-sqlite "
        '(pip install -e ".[persist]")'
    )


def build_checkpointer(cfg: HarnessConfig):
    kind = (cfg.persist.checkpointer or "memory").lower()
    if kind == "memory":
        return MemorySaver()
    if kind == "sqlite":
        path = _expand(cfg.persist.checkpointer_path or "~/.harness/checkpoints.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError(_sqlite_import_error("checkpointer")) from exc
        conn = sqlite3.connect(str(path), check_same_thread=False)
        _HELD.append(conn)
        saver = SqliteSaver(conn)
        saver.setup()
        return saver
    raise ValueError(f"unknown persist.checkpointer: {kind}")


def build_store(cfg: HarnessConfig):
    kind = (cfg.persist.store or "memory").lower()
    if kind == "memory":
        return InMemoryStore()
    if kind == "sqlite":
        path = _expand(cfg.persist.store_path or "~/.harness/store.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from langgraph.store.sqlite import SqliteStore
        except ImportError as exc:
            raise RuntimeError(_sqlite_import_error("store")) from exc
        conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        _HELD.append(conn)
        store = SqliteStore(conn)
        store.setup()
        return store
    raise ValueError(f"unknown persist.store: {kind}")


async def build_checkpointer_async(cfg: HarnessConfig):
    """Async graph (astream) needs AsyncSqliteSaver, not the sync context manager."""
    kind = (cfg.persist.checkpointer or "memory").lower()
    if kind != "sqlite":
        return build_checkpointer(cfg)
    path = _expand(cfg.persist.checkpointer_path or "~/.harness/checkpoints.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError as exc:
        raise RuntimeError(_sqlite_import_error("checkpointer")) from exc
    conn = await aiosqlite.connect(str(path))
    _HELD.append(conn)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver


async def build_store_async(cfg: HarnessConfig):
    kind = (cfg.persist.store or "memory").lower()
    if kind != "sqlite":
        return build_store(cfg)
    path = _expand(cfg.persist.store_path or "~/.harness/store.sqlite")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import aiosqlite
        from langgraph.store.sqlite.aio import AsyncSqliteStore
    except ImportError as exc:
        raise RuntimeError(_sqlite_import_error("store")) from exc
    conn = await aiosqlite.connect(str(path), isolation_level=None)
    _HELD.append(conn)
    store = AsyncSqliteStore(conn)
    await store.setup()
    return store
