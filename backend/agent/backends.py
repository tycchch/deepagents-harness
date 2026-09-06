from __future__ import annotations

import shutil
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend

from agent.sandbox import DockerSandboxBackend
from config.schema import HarnessConfig


def build_backend(cfg: HarnessConfig, *, context=None) -> CompositeBackend:
    del context
    workspace = Path(cfg.workspace_root or Path.cwd()).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    skills_root = Path(cfg.skills_root or Path.home() / ".harness" / "skills").resolve()
    shared = skills_root / "shared"
    personal = skills_root / "personal"
    memories = Path(cfg.memories_root or Path.home() / ".harness" / "memories").resolve()
    for path in (shared, personal, memories):
        path.mkdir(parents=True, exist_ok=True)
    _seed_shared_skills(shared)

    routes: dict = {
        "/skills/shared/": FilesystemBackend(root_dir=shared, virtual_mode=True),
        "/skills/personal/": FilesystemBackend(root_dir=personal, virtual_mode=True),
        "/memories/": FilesystemBackend(root_dir=memories, virtual_mode=True),
    }
    if cfg.sandbox.enabled:
        routes["/workspace/"] = DockerSandboxBackend(
            workdir=cfg.sandbox.workdir,
            image=cfg.sandbox.image,
        )
    else:
        routes["/workspace/"] = FilesystemBackend(root_dir=workspace, virtual_mode=True)

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
