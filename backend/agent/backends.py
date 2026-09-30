from __future__ import annotations

import shutil
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.backends.protocol import BackendProtocol

from agent.file_history import BlobStore, FileHistoryBackend
from agent.sandbox import DockerSandboxBackend
from config.schema import HarnessConfig


def build_backend(
    cfg: HarnessConfig,
    *,
    context=None,
    blobs: BlobStore | None = None,
) -> CompositeBackend:
    del context
    workspace = Path(cfg.workspace_root or Path.cwd()).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    skills_root = Path(cfg.skills_root or Path.home() / ".harness" / "skills").resolve()
    shared = skills_root / "shared"
    personal = skills_root / "personal"
    memories = Path(cfg.memories_root or Path.home() / ".harness" / "memories").resolve()
    history = memories.parent / "conversation_history"
    large_results = memories.parent / "large_tool_results"
    for path in (shared, personal, memories, history, large_results):
        path.mkdir(parents=True, exist_ok=True)
    _seed_shared_skills(shared)

    routes: dict = {
        "/skills/shared/": FilesystemBackend(root_dir=shared, virtual_mode=True),
        "/skills/personal/": FilesystemBackend(root_dir=personal, virtual_mode=True),
        "/memories/": FilesystemBackend(root_dir=memories, virtual_mode=True),
        "/conversation_history/": FilesystemBackend(root_dir=history, virtual_mode=True),
        "/large_tool_results/": FilesystemBackend(root_dir=large_results, virtual_mode=True),
    }
    if cfg.sandbox.enabled:
        # 沙箱模式下 /workspace/ 在容器里，这一版不做备份。
        routes["/workspace/"] = DockerSandboxBackend(
            workdir=cfg.sandbox.workdir,
            image=cfg.sandbox.image,
        )
    else:
        workspace_backend: BackendProtocol = FilesystemBackend(
            root_dir=workspace, virtual_mode=True
        )
        if blobs is not None:
            # 必须在 CompositeBackend 构造前替换：sorted_routes 是构造时快照的，
            # 之后再改 routes 不会影响路由。
            workspace_backend = FileHistoryBackend(workspace_backend, blobs)
        routes["/workspace/"] = workspace_backend

    return CompositeBackend(default=StateBackend(), routes=routes)


def _seed_shared_skills(shared: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "skills"
    if not src.is_dir():
        return
    for item in src.iterdir():
        dest = shared / item.name
        if dest.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
