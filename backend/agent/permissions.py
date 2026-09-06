from deepagents import FilesystemPermission

from config.schema import HarnessConfig


def build_permissions(_cfg: HarnessConfig) -> list[FilesystemPermission]:
    return [
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/workspace/.env", "/workspace/**/.env", "/workspace/examples/**"],
            mode="deny",
        ),
        FilesystemPermission(
            operations=["write"],
            paths=["/skills/shared/**", "/policies/**"],
            mode="deny",
        ),
        FilesystemPermission(
            operations=["write"],
            paths=["/skills/personal/**"],
            mode="interrupt",
        ),
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/workspace", "/workspace/", "/workspace/**"],
            mode="allow",
        ),
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/memories", "/memories/", "/memories/**"],
            mode="allow",
        ),
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/**"],
            mode="deny",
        ),
    ]


def build_interrupt_on(_cfg: HarnessConfig) -> dict:
    return {
        "execute": {"allowed_decisions": ["approve", "edit", "reject"]},
        "write_file": {
            "allowed_decisions": ["approve", "edit", "reject"],
            "when": _writes_outside_workspace,
        },
        "edit_file": True,
        "delete": True,
        "read_file": False,
        "ls": False,
    }


def _writes_outside_workspace(request) -> bool:
    args = request.tool_call.get("args", {}) if hasattr(request, "tool_call") else {}
    path = str(args.get("file_path") or args.get("path") or "")
    return not path.startswith("/workspace/")
