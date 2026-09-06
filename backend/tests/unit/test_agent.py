from pathlib import Path
from unittest.mock import patch

from config.schema import HarnessConfig, SandboxConfig
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.backends.filesystem import FilesystemBackend as FS


def test_permissions_first_match_and_personal_interrupt(tmp_path: Path) -> None:
    from agent.permissions import build_permissions

    cfg = HarnessConfig(workspace_root=str(tmp_path))
    rules = build_permissions(cfg)
    assert rules[0].mode == "deny"
    assert "/workspace/.env" in rules[0].paths
    shared = next(r for r in rules if "/skills/shared/**" in r.paths)
    assert shared.mode == "deny"
    assert "write" in shared.operations
    personal = next(r for r in rules if "/skills/personal/**" in r.paths)
    assert personal.mode == "interrupt"
    memories = next(r for r in rules if "/memories/**" in r.paths)
    assert memories.mode == "allow"
    assert "/memories" in memories.paths
    assert rules[-1].paths == ["/**"]
    assert rules[-1].mode == "deny"


def test_interrupt_on_covers_execute(tmp_path: Path) -> None:
    from agent.permissions import build_interrupt_on

    hitl = build_interrupt_on(HarnessConfig(workspace_root=str(tmp_path)))
    assert "execute" in hitl
    assert hitl["execute"]["allowed_decisions"] == ["approve", "edit", "reject"]
    assert hitl["read_file"] is False


def test_backend_routes_workspace_to_filesystem(tmp_path: Path) -> None:
    from agent.backends import build_backend

    workspace = tmp_path / "ws"
    workspace.mkdir()
    skills = tmp_path / "skills"
    cfg = HarnessConfig(workspace_root=str(workspace), skills_root=str(skills))
    backend = build_backend(cfg)
    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.default, StateBackend)
    assert isinstance(backend.routes["/workspace/"], (FilesystemBackend, FS))
    assert isinstance(backend.routes["/skills/shared/"], (FilesystemBackend, FS))
    assert isinstance(backend.routes["/skills/personal/"], (FilesystemBackend, FS))
    assert "/workspace/" in backend.routes
    assert not isinstance(backend.default, type(backend.routes["/workspace/"])) or isinstance(
        backend.default, StateBackend
    )


def test_backend_sandbox_not_default(tmp_path: Path) -> None:
    from agent.backends import build_backend
    from agent.sandbox import DockerSandboxBackend

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(
        workspace_root=str(workspace),
        skills_root=str(tmp_path / "skills"),
        sandbox=SandboxConfig(enabled=True),
    )
    backend = build_backend(cfg)
    assert isinstance(backend.routes["/workspace/"], DockerSandboxBackend)
    assert isinstance(backend.default, StateBackend)


def test_factory_passes_skills_permissions_and_name(tmp_path: Path) -> None:
    from agent.factory import create_harness_agent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    cfg = HarnessConfig(workspace_root=str(workspace), skills_root=str(tmp_path / "skills"))
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return object()

    with patch("agent.factory.create_deep_agent", side_effect=lambda *a, **k: fake_create(**k)):
        agent = create_harness_agent(cfg)

    assert agent is not None
    assert captured["name"] == "harness"
    assert captured["skills"] == ["/skills/shared/", "/skills/personal/"]
    assert captured["permissions"]
    assert captured["interrupt_on"]
    assert captured["checkpointer"] is not None
    assert captured["store"] is not None
    assert captured["backend"] is not None
    assert str(workspace) in captured["system_prompt"]
    assert "/workspace/" in captured["system_prompt"]
