from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from config.schema import HarnessConfig
from protocol.frame import RpcError, RpcNotification, RpcRequest, RpcResponse, dumps_message, parse_message
from protocol.methods import (
    ApprovalResolveParams,
    ConfigSetParams,
    InitializeParams,
    InitializeResult,
    SkillsWriteParams,
    ThreadResumeParams,
    ThreadStartParams,
    TurnInterruptParams,
    TurnStartParams,
)
from server.session import ThreadStore
from server.stream import AgentTurnStreamer, ApprovalHub, FakeTurnStreamer, TurnRunner


class RpcDispatchError(Exception):
    def __init__(self, message: str, code: int = -32000) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RpcDispatcher:
    def __init__(
        self,
        *,
        store: ThreadStore | None = None,
        skills_root: str | Path | None = None,
        runner: TurnRunner | None = None,
        agent=None,
        cfg: HarnessConfig | None = None,
    ) -> None:
        self._initialized = False
        self._threads = store or ThreadStore()
        self._skills_root = Path(skills_root) if skills_root else Path.home() / ".harness" / "skills"
        self._cfg = cfg
        self._config = (cfg or HarnessConfig()).model_dump(mode="json")
        self._agent = agent
        self._approvals = ApprovalHub()
        self._streamer = FakeTurnStreamer()
        if runner is not None:
            self._runner = runner
        elif agent is not None:
            self._runner = TurnRunner(AgentTurnStreamer(agent))
        else:
            self._runner = TurnRunner()

    def handle(self, raw: str) -> list[str]:
        message = parse_message(raw)
        if not isinstance(message, RpcRequest):
            return []
        try:
            result, extras = self._dispatch(message)
        except RpcDispatchError as exc:
            return [
                dumps_message(RpcResponse(id=message.id, error=RpcError(code=exc.code, message=exc.message)))
            ]
        out = [dumps_message(item) for item in extras]
        out.append(dumps_message(RpcResponse(id=message.id, result=result)))
        return out

    async def ahandle(self, raw: str) -> list[str]:
        return [item async for item in self.ahandle_stream(raw)]

    async def ahandle_stream(self, raw: str) -> AsyncIterator[str]:
        message = parse_message(raw)
        if not isinstance(message, RpcRequest):
            return
        if message.method != "turn/start":
            for item in self.handle(raw):
                yield item
            return
        try:
            thread_id, text = await self._prepare_turn(message)
            async for note in self._runner.stream(thread_id, text):
                yield dumps_message(note)
            yield dumps_message(RpcResponse(id=message.id, result={}))
        except RpcDispatchError as exc:
            yield dumps_message(RpcResponse(id=message.id, error=RpcError(code=exc.code, message=exc.message)))
        except Exception as exc:
            yield dumps_message(
                RpcResponse(id=message.id, error=RpcError(code=-32000, message=str(exc)))
            )

    async def _ensure_agent(self, workspace: str) -> None:
        if self._agent is not None:
            return
        if self._cfg is None or not self._cfg.deepseek_api_key:
            return
        from agent.factory import create_harness_agent
        from config.persist import build_checkpointer_async, build_store_async

        updated = self._cfg.model_copy(update={"workspace_root": workspace or self._cfg.workspace_root})
        checkpointer = await build_checkpointer_async(updated)
        store = await build_store_async(updated)
        self._agent = create_harness_agent(updated, store=store, checkpointer=checkpointer)
        self._runner = TurnRunner(AgentTurnStreamer(self._agent))

    async def _prepare_turn(self, request: RpcRequest) -> tuple[str, str]:
        if not self._initialized:
            raise RpcDispatchError("Not initialized")
        params = TurnStartParams.model_validate(request.params)
        info = self._threads.get(params.thread_id)
        if info is None:
            raise RpcDispatchError("Unknown thread")
        await self._ensure_agent(info.workspace)
        if self._runner.is_busy(params.thread_id):
            raise RpcDispatchError("Turn already running")
        self._threads.touch(params.thread_id, title=params.text[:40])
        return params.thread_id, params.text

    def _public_config(self) -> dict:
        data = dict(self._config)
        if data.get("deepseek_api_key"):
            data["deepseek_api_key"] = "***"
        return data

    def _dispatch(self, request: RpcRequest) -> tuple[dict, list[RpcNotification]]:
        if request.method != "initialize" and not self._initialized:
            raise RpcDispatchError("Not initialized")

        if request.method == "initialize":
            InitializeParams.model_validate(request.params)
            self._initialized = True
            return InitializeResult().model_dump(mode="json"), []

        if request.method == "thread/start":
            params = ThreadStartParams.model_validate(request.params)
            return self._threads.start(params.workspace).model_dump(mode="json"), []

        if request.method == "thread/resume":
            params = ThreadResumeParams.model_validate(request.params)
            info = self._threads.resume(params.thread_id)
            if info is None:
                raise RpcDispatchError("Unknown thread")
            return info.model_dump(mode="json"), []

        if request.method == "thread/list":
            include_archived = bool(request.params.get("include_archived"))
            return {
                "threads": [
                    item.model_dump(mode="json")
                    for item in self._threads.list(include_archived=include_archived)
                ]
            }, []

        if request.method == "thread/archive":
            params = ThreadResumeParams.model_validate(request.params)
            if not self._threads.archive(params.thread_id):
                raise RpcDispatchError("Unknown thread")
            return {}, []

        if request.method == "thread/unarchive":
            params = ThreadResumeParams.model_validate(request.params)
            if not self._threads.unarchive(params.thread_id):
                raise RpcDispatchError("Unknown thread")
            return {}, []

        if request.method == "turn/start":
            params = TurnStartParams.model_validate(request.params)
            if self._threads.get(params.thread_id) is None:
                raise RpcDispatchError("Unknown thread")
            if self._runner.is_busy(params.thread_id):
                raise RpcDispatchError("Turn already running")
            self._threads.touch(params.thread_id, title=params.text[:40])
            return {}, self._streamer.sync_events(params.text)

        if request.method == "turn/interrupt":
            params = TurnInterruptParams.model_validate(request.params)
            if self._threads.get(params.thread_id) is None and not self._runner.is_busy(params.thread_id):
                raise RpcDispatchError("Unknown thread")
            if not self._runner.interrupt(params.thread_id):
                raise RpcDispatchError("No running turn")
            return {}, []

        if request.method == "approval/resolve":
            params = ApprovalResolveParams.model_validate(request.params)
            try:
                self._approvals.resolve(params)
            except KeyError as exc:
                raise RpcDispatchError("Unknown approval") from exc
            return {}, []

        if request.method == "skills/list":
            return {"skills": _list_skills(self._skills_root)}, []

        if request.method == "skills/read":
            path = str(request.params.get("path", ""))
            file_path = _skill_disk_path(self._skills_root, path)
            if file_path is None or not file_path.is_file():
                raise RpcDispatchError("Unknown skill")
            return {"path": path, "content": file_path.read_text(encoding="utf-8")}, []

        if request.method == "skills/write":
            params = SkillsWriteParams.model_validate(request.params)
            if not params.path.startswith("/skills/personal/"):
                raise RpcDispatchError("Personal skills only")
            file_path = _skill_disk_path(self._skills_root, params.path)
            if file_path is None:
                raise RpcDispatchError("Invalid skill path")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(params.content, encoding="utf-8")
            return {}, []

        if request.method == "config/get":
            return {"config": self._public_config()}, []

        if request.method == "config/set":
            params = ConfigSetParams.model_validate(request.params)
            self._config.update(params.values)
            return {"config": self._public_config()}, []

        raise RpcDispatchError(f"Unknown method: {request.method}", code=-32601)


def _skill_disk_path(root: Path, virtual: str) -> Path | None:
    if virtual.startswith("/skills/personal/"):
        scope, rel = "personal", virtual.removeprefix("/skills/personal/")
    elif virtual.startswith("/skills/shared/"):
        scope, rel = "shared", virtual.removeprefix("/skills/shared/")
    else:
        return None
    base = (root / scope).resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        return None
    return path


def _list_skills(root: Path) -> list[dict]:
    found: list[dict] = []
    for scope in ("shared", "personal"):
        base = root / scope
        if not base.is_dir():
            continue
        for skill_md in base.glob("*/SKILL.md"):
            found.append(
                {
                    "name": skill_md.parent.name,
                    "scope": scope,
                    "path": f"/skills/{scope}/{skill_md.parent.name}/SKILL.md",
                }
            )
    return found
