from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

_IGNORED_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "dist",
        "dist-electron",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    }
)


class WorkspaceSnapshotStore:
    """Content-addressed workspace snapshots, materialized on fork."""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else None

    def capture(self, workspace: str | Path) -> str | None:
        if self._root is None:
            return None
        source = Path(workspace).resolve()
        if not source.is_dir():
            return None
        entries: dict[str, str] = {}
        for path in source.rglob("*"):
            relative = path.relative_to(source)
            if _IGNORED_PARTS.intersection(relative.parts) or not path.is_file():
                continue
            content = path.read_bytes()
            blob_id = hashlib.sha256(content).hexdigest()
            self._put_blob(blob_id, content)
            entries[relative.as_posix()] = blob_id
        manifest_id = uuid4().hex
        manifest = {"workspace": str(source), "files": entries}
        target = self._manifest_path(manifest_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)
        return manifest_id

    def materialize(self, manifest_id: str, destination: str | Path) -> Path:
        target = Path(destination).resolve()
        if target.exists():
            raise FileExistsError(target)
        data = json.loads(self._manifest_path(manifest_id).read_text(encoding="utf-8"))
        target.mkdir(parents=True)
        for relative, blob_id in data["files"].items():
            output = (target / relative).resolve()
            if not output.is_relative_to(target):
                raise ValueError(f"invalid manifest path: {relative}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(self._blob_path(str(blob_id)).read_bytes())
        return target

    def fork_path(self, workspace: str | Path, thread_id: str) -> Path:
        if self._root is not None:
            return self._root / "workspaces" / thread_id
        source = Path(workspace).resolve()
        return source.parent / f"{source.name}.harness-forks" / thread_id

    def _put_blob(self, blob_id: str, content: bytes) -> None:
        target = self._blob_path(blob_id)
        if target.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)

    def _manifest_path(self, manifest_id: str) -> Path:
        if self._root is None or len(manifest_id) != 32:
            raise ValueError(f"invalid manifest id: {manifest_id!r}")
        return self._root / "manifests" / f"{manifest_id}.json"

    def _blob_path(self, blob_id: str) -> Path:
        if self._root is None or len(blob_id) != 64:
            raise ValueError(f"invalid blob id: {blob_id!r}")
        return self._root / "blobs" / blob_id[:2] / blob_id
