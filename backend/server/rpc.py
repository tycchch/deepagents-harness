from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from config.providers import ProviderStore
from config.schema import HarnessConfig
from protocol.frame import (
    RpcError,
    RpcNotification,
    RpcRequest,
    RpcResponse,
    dumps_message,
    parse_message,
)
from protocol.methods import (
    ApprovalResolveParams,
    ClientType,
    ConfigSetParams,
    InitializeParams,
    InitializeResult,
    ModelsSetParams,
    ProviderDeleteParams,
    ProviderUpsertParams,
    SkillsWriteParams,
    ThreadForkParams,
    ThreadRenameParams,
    ThreadResumeParams,
    ThreadSetWorkspaceParams,
    ThreadStartParams,
    TurnInterruptParams,
    TurnStartParams,
)
from server.checkpoints import clone_checkpoint
from server.session import ThreadStore, normalize_workspace
from server.stream import (
    AgentTurnStreamer,
    ApprovalHub,
    FakeTurnStreamer,
    TurnRunner,
    delete_thread_state,
    thread_history,
)
from server.turns import TurnStore
from server.workspaces import WorkspaceSnapshotStore

logger = logging.getLogger(__name__)

# One agent per workspace for the whole process: each connection sharing the same
# checkpointer is what makes history survive page reloads (and avoids leaking sqlite conns).
_AGENTS: dict[str, object] = {}
_AGENT_SIG: dict[str, str] = {}
_PERSIST: dict[str, tuple[object, object]] = {}
_AGENT_LOCK = asyncio.Lock()


# 当前模型配置的指纹：一旦变化，说明缓存里的 agent 已过期，必须重建。
def _model_sig(cfg: HarnessConfig) -> str:
    return "|".join(
        [
            cfg.provider_protocol,
            cfg.deepseek_base_url,
            cfg.deepseek_model or cfg.model,
            "1" if cfg.deepseek_api_key else "0",
            str(cfg.context_limit_tokens),
        ]
    )


# 清空 agent 缓存；切换模型 / 增删 provider 后调用，强制下次按新配置重建。
def invalidate_agents() -> None:
    _AGENTS.clear()
    _AGENT_SIG.clear()


# 取（或建）某个 workspace 的共享 agent：同一 workspace 复用同一个 agent 与 checkpointer，
# 这样历史能跨页面刷新存活，也避免重复打开 sqlite 连接。
async def _shared_agent(cfg: HarnessConfig, workspace: str):
    from agent.factory import create_harness_agent
    from config.persist import build_checkpointer_async, build_store_async

    key = normalize_workspace(workspace or cfg.workspace_root)
    updated = cfg.model_copy(update={"workspace_root": key})
    sig = _model_sig(updated)
    async with _AGENT_LOCK:
        agent = _AGENTS.get(key)
        if agent is not None and _AGENT_SIG.get(key) == sig:
            return agent
        persist = _PERSIST.get(key)
        if persist is None:
            checkpointer = await build_checkpointer_async(updated)
            store = await build_store_async(updated)
            _PERSIST[key] = (checkpointer, store)
        else:
            checkpointer, store = persist
        agent = create_harness_agent(updated, store=store, checkpointer=checkpointer)
        _AGENTS[key] = agent
        _AGENT_SIG[key] = sig
        return agent


class RpcDispatchError(Exception):
    def __init__(self, message: str, code: int = -32000) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RpcDispatcher:
    """把一条 JSON-RPC 请求字符串路由到具体动作，并产出要发回客户端的字符串。

    它只认字符串、只吐字符串，不碰 WebSocket —— 真正的收发在网络层 app.py 里。
    """

    # 构造时装配：会话元数据(ThreadStore) / 轮次索引(TurnStore) / 工作区快照(WorkspaceSnapshotStore)
    # 以及运行时对象（runner、streamer、approvals）。
    # store= / turns= / workspaces= / runner= 等可选参数是留给测试替换的注入口。
    def __init__(
        self,
        *,
        store: ThreadStore | None = None,
        skills_root: str | Path | None = None,
        runner: TurnRunner | None = None,
        agent=None,
        cfg: HarnessConfig | None = None,
        providers: ProviderStore | None = None,
        turns: TurnStore | None = None,
        workspaces: WorkspaceSnapshotStore | None = None,
    ) -> None:
        self._initialized = False
        self._client = ClientType.DESKTOP
        self._threads = store or ThreadStore()
        turn_path = self._threads.path.with_name("turns.sqlite") if self._threads.path else None
        self._turns = turns or TurnStore(turn_path)
        snapshot_root = turn_path.parent / "workspace_snapshots" if turn_path else None
        self._workspaces = workspaces or WorkspaceSnapshotStore(snapshot_root)
        self._skills_root = Path(skills_root) if skills_root else Path.home() / ".harness" / "skills"
        self._providers = providers
        self._cfg = cfg
        if cfg is not None:
            self._providers_store().seed_from_cfg(cfg)
            self._cfg = self._providers_store().apply(cfg)
        self._config = (self._cfg or HarnessConfig()).model_dump(mode="json")
        self._agent = agent
        self._approvals = ApprovalHub()
        self._streamer = FakeTurnStreamer()
        if runner is not None:
            self._runner = runner
        elif agent is not None:
            self._runner = TurnRunner(AgentTurnStreamer(agent))
        else:
            self._runner = TurnRunner()

    # 同步入口：一次返回全部输出（含 extras 通知）。
    # 不支持需要流式的 thread/history、thread/delete、thread/fork。
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

    # 异步入口：把流式结果收集成完整列表再返回，方便测试和不关心流的调用方。
    async def ahandle(self, raw: str) -> list[str]:
        return [item async for item in self.ahandle_stream(raw)]

    # 真正的主入口：app.py 收到的每条 ws 消息都走这里。
    # turn/start、thread/history、thread/delete、thread/fork 需要流式或多步处理，单独特判；
    # 其余方法一律交给同步的 handle()。
    async def ahandle_stream(self, raw: str) -> AsyncIterator[str]:
        message = parse_message(raw)
        if not isinstance(message, RpcRequest):
            return
        if message.method not in {
            "turn/start",
            "thread/history",
            "thread/delete",
            "thread/fork",
        }:
            for item in self.handle(raw):
                yield item
            return
        try:
            # 拉取某个会话的完整历史：从 checkpointer 读消息并转成 ItemEvent 列表。
            if message.method == "thread/history":
                yield dumps_message(RpcResponse(id=message.id, result=await self._thread_history(message)))
                return
            # 删除会话：先打断在跑的轮次，再清 checkpointer 状态、轮次索引和元数据。
            if message.method == "thread/delete":
                yield dumps_message(RpcResponse(id=message.id, result=await self._thread_delete(message)))
                return
            # 从历史某一轮分叉出新会话：克隆该轮的 checkpoint，并复刻工作区快照。
            if message.method == "thread/fork":
                result = await self._thread_fork(message)
                yield dumps_message(RpcResponse(id=message.id, result=result))
                return
            # turn/start：校验 + 记一条 turn，然后流式跑 agent，把每条通知逐条 yield 给客户端。
            thread_id, text, turn_id = await self._prepare_turn(message)
            async for note in self._runner.stream(thread_id, text, turn_id):
                if note.method.startswith("item/"):
                    note.params.setdefault("turn_id", turn_id)
                if note.method == "turn/completed":
                    status = str(note.params.get("status") or "completed")
                    checkpoint_id = note.params.get("checkpoint_id")
                    manifest_id = None
                    if status == "completed" and checkpoint_id:
                        info = self._threads.get(thread_id)
                        if info is not None:
                            try:
                                manifest_id = await asyncio.to_thread(
                                    self._workspaces.capture, info.workspace
                                )
                            except Exception:
                                logger.warning(
                                    "unable to capture workspace for turn %s",
                                    turn_id,
                                    exc_info=True,
                                )
                    self._turns.finish(
                        turn_id,
                        status=status,
                        checkpoint_id=str(checkpoint_id) if checkpoint_id else None,
                        workspace_manifest_id=manifest_id,
                    )
                yield dumps_message(note)
            yield dumps_message(RpcResponse(id=message.id, result={"turn_id": turn_id}))
        except RpcDispatchError as exc:
            yield dumps_message(RpcResponse(id=message.id, error=RpcError(code=exc.code, message=exc.message)))
        except Exception as exc:
            yield dumps_message(
                RpcResponse(id=message.id, error=RpcError(code=-32000, message=str(exc)))
            )

    # thread/delete 的实现：元数据是权威，checkpoint 只是缓存，删除失败也照常继续。
    async def _thread_delete(self, request: RpcRequest) -> dict:
        if not self._initialized:
            raise RpcDispatchError("Not initialized")
        params = ThreadResumeParams.model_validate(request.params)
        info = self._threads.get(params.thread_id)
        if info is None:
            raise RpcDispatchError("Unknown thread")
        self._runner.interrupt(params.thread_id)
        await self._ensure_agent(info.workspace)
        await delete_thread_state(self._agent, params.thread_id)
        self._turns.delete_thread(params.thread_id)
        self._threads.delete(params.thread_id)
        return {}

    # thread/history 的实现：只回放"已完成"轮次的历史消息，running 中的不含。
    async def _thread_history(self, request: RpcRequest) -> dict:
        if not self._initialized:
            raise RpcDispatchError("Not initialized")
        params = ThreadResumeParams.model_validate(request.params)
        info = self._threads.get(params.thread_id)
        if info is None:
            raise RpcDispatchError("Unknown thread")
        await self._ensure_agent(info.workspace)
        turns = self._visible_turns(params.thread_id)
        items = await thread_history(
            self._agent,
            params.thread_id,
            [turn.turn_id for turn in turns if turn.status == "completed"],
        )
        return {"items": [item.model_dump(mode="json") for item in items]}

    # thread/fork 的实现：要求源轮次是 completed 且带有 checkpoint 与工作区快照，
    # 否则无法分叉；成功后以该 turn_id 为分叉点建出子会话。
    async def _thread_fork(self, request: RpcRequest) -> dict:
        if not self._initialized:
            raise RpcDispatchError("Not initialized")
        params = ThreadForkParams.model_validate(request.params)
        source_info = self._threads.get(params.thread_id)
        if source_info is None:
            raise RpcDispatchError("Unknown thread")
        if self._runner.is_busy(params.thread_id):
            raise RpcDispatchError("Cannot fork a running thread")
        visible_ids = {turn.turn_id for turn in self._visible_turns(params.thread_id)}
        turn = self._turns.get(params.turn_id)
        if turn is None or turn.turn_id not in visible_ids:
            raise RpcDispatchError("Unknown turn")
        if turn.status != "completed" or not turn.checkpoint_id:
            raise RpcDispatchError("Turn has no completed checkpoint")
        if not turn.workspace_manifest_id:
            raise RpcDispatchError("Turn has no workspace snapshot")

        owner = self._threads.get(turn.thread_id)
        if owner is None:
            raise RpcDispatchError("Turn owner is missing")
        source_agent = await self._agent_for_workspace(owner.workspace)
        if source_agent is None or getattr(source_agent, "checkpointer", None) is None:
            raise RpcDispatchError("Checkpoint storage is unavailable")

        child_id = str(uuid4())
        destination = self._workspaces.fork_path(source_info.workspace, child_id)
        await asyncio.to_thread(
            self._workspaces.materialize,
            turn.workspace_manifest_id,
            destination,
        )
        target_agent = await self._agent_for_workspace(str(destination))
        if target_agent is None or getattr(target_agent, "checkpointer", None) is None:
            raise RpcDispatchError("Target checkpoint storage is unavailable")
        await clone_checkpoint(
            source_agent.checkpointer,
            target_agent.checkpointer,
            source_thread_id=turn.thread_id,
            source_checkpoint_id=turn.checkpoint_id,
            target_thread_id=child_id,
        )
        info = self._threads.fork(
            params.thread_id,
            params.turn_id,
            str(destination),
            child_id=child_id,
        )
        if info is None:
            raise RpcDispatchError("Unknown thread")
        return info.model_dump(mode="json")

    # 计算会话"可见"的全部轮次：fork 出来的会话 = 父链到分叉点为止 + 自己的轮次。
    # seen 用于检测父链是否成环。
    def _visible_turns(self, thread_id: str, seen: set[str] | None = None):
        seen = set(seen or ())
        if thread_id in seen:
            raise RpcDispatchError("Thread ancestry cycle")
        seen.add(thread_id)
        info = self._threads.get(thread_id)
        if info is None:
            return []
        own = self._turns.list_for_thread(thread_id)
        if not info.parent_thread_id or not info.forked_from_turn_id:
            return own
        parent = self._visible_turns(info.parent_thread_id, seen)
        prefix = []
        for turn in parent:
            prefix.append(turn)
            if turn.turn_id == info.forked_from_turn_id:
                break
        return [*prefix, *own]

    # 按 workspace 取 agent；未配置（或无 api key）时退回当前实例 self._agent。
    async def _agent_for_workspace(self, workspace: str):
        if self._cfg is None:
            return self._agent
        self._apply_providers()
        if not self._cfg.deepseek_api_key:
            return self._agent
        return await _shared_agent(self._cfg, workspace)

    # 懒加载 provider 存储：配置里没注入就现场建一个。
    def _providers_store(self) -> ProviderStore:
        if self._providers is None:
            self._providers = ProviderStore()
        return self._providers

    # 把 provider 存储里选中的模型/供应商回写到 self._cfg 和 self._config。
    def _apply_providers(self) -> None:
        if self._cfg is None:
            return
        self._cfg = self._providers_store().apply(self._cfg)
        self._config = self._cfg.model_dump(mode="json")

    # 确保当前 agent 与 workspace 匹配；若切到新 agent，顺带把 runner 换成真流式实现。
    async def _ensure_agent(self, workspace: str) -> None:
        if self._cfg is None:
            return
        self._apply_providers()
        if not self._cfg.deepseek_api_key:
            return
        agent = await _shared_agent(self._cfg, workspace)
        if agent is self._agent:
            return
        self._agent = agent
        self._runner = TurnRunner(AgentTurnStreamer(self._agent))

    # 开跑一轮前的准备：校验已初始化、会话存在、且没有正在跑的轮次；
    # 然后更新会话标题、在 TurnStore 记一条 running，返回 (thread_id, text, turn_id)。
    async def _prepare_turn(self, request: RpcRequest) -> tuple[str, str, str]:
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
        turn = self._turns.start(params.thread_id)
        return params.thread_id, params.text, turn.turn_id

    # 返回给客户端的配置：api_key 打码成 ***。
    def _public_config(self) -> dict:
        self._apply_providers()
        data = dict(self._config)
        if data.get("deepseek_api_key"):
            data["deepseek_api_key"] = "***"
        return data

    # _dispatch方法是RpcDispatcher类的核心方法，用于处理RPC请求。
    # 它根据请求的方法名调用相应的处理逻辑，并返回结果和可能的额外通知。
    # —— 下面每个 if 分支就是一个可被客户端触发的动作，method 名即路由键。
    def _dispatch(self, request: RpcRequest) -> tuple[dict, list[RpcNotification]]:
        if request.method != "initialize" and not self._initialized:
            raise RpcDispatchError("Not initialized")

        # initialize：握手；此后所有请求都要求先初始化过。
        if request.method == "initialize":
            params = InitializeParams.model_validate(request.params)
            self._initialized = True
            self._client = params.client
            return InitializeResult().model_dump(mode="json"), []

        # thread/start：新建一个会话（绑定 workspace），返回 ThreadInfo。
        if request.method == "thread/start":
            params = ThreadStartParams.model_validate(request.params)
            return self._threads.start(params.workspace, source=self._client.value).model_dump(mode="json"), []

        # thread/resume：按 id 取回会话元数据。
        if request.method == "thread/resume":
            params = ThreadResumeParams.model_validate(request.params)
            info = self._threads.resume(params.thread_id)
            if info is None:
                raise RpcDispatchError("Unknown thread")
            return info.model_dump(mode="json"), []

        # thread/list：列出会话；默认只看当前来源（cli/desktop），可含归档。
        if request.method == "thread/list":
            include_archived = bool(request.params.get("include_archived"))
            include_all = bool(request.params.get("include_all_sources"))
            source = None if include_all else str(request.params.get("source") or self._client.value)
            return {
                "threads": [
                    item.model_dump(mode="json")
                    for item in self._threads.list(include_archived=include_archived, source=source)
                ]
            }, []

        # thread/set_workspace：改会话绑定的工作目录。
        if request.method == "thread/set_workspace":
            params = ThreadSetWorkspaceParams.model_validate(request.params)
            info = self._threads.set_workspace(params.thread_id, params.workspace)
            if info is None:
                raise RpcDispatchError("Unknown thread")
            return info.model_dump(mode="json"), []

        # thread/rename：手动改标题（改过之后不再被首条消息自动覆盖）。
        if request.method == "thread/rename":
            params = ThreadRenameParams.model_validate(request.params)
            info = self._threads.rename(params.thread_id, params.title)
            if info is None:
                raise RpcDispatchError("Unknown thread")
            return info.model_dump(mode="json"), []

        # thread/archive：归档（隐藏但保留）。
        if request.method == "thread/archive":
            params = ThreadResumeParams.model_validate(request.params)
            if not self._threads.archive(params.thread_id):
                raise RpcDispatchError("Unknown thread")
            return {}, []

        # thread/unarchive：取消归档。
        if request.method == "thread/unarchive":
            params = ThreadResumeParams.model_validate(request.params)
            if not self._threads.unarchive(params.thread_id):
                raise RpcDispatchError("Unknown thread")
            return {}, []

        # turn/start（同步回退路径）：未接真 agent 时用 FakeTurnStreamer 立即回显。
        # 注意：走 ws 时 turn/start 会被 ahandle_stream 截走，不会走到这里。
        if request.method == "turn/start":
            params = TurnStartParams.model_validate(request.params)
            if self._threads.get(params.thread_id) is None:
                raise RpcDispatchError("Unknown thread")
            if self._runner.is_busy(params.thread_id):
                raise RpcDispatchError("Turn already running")
            self._threads.touch(params.thread_id, title=params.text[:40])
            turn = self._turns.start(params.thread_id)
            notes = self._streamer.sync_events(params.text, turn.turn_id)
            self._turns.finish(turn.turn_id, status="completed")
            return {"turn_id": turn.turn_id}, notes

        # turn/interrupt：打断该会话正在跑的轮次。
        if request.method == "turn/interrupt":
            params = TurnInterruptParams.model_validate(request.params)
            if self._threads.get(params.thread_id) is None and not self._runner.is_busy(params.thread_id):
                raise RpcDispatchError("Unknown thread")
            if not self._runner.interrupt(params.thread_id):
                raise RpcDispatchError("No running turn")
            return {}, []

        # approval/resolve：客户端回答一个审批请求，唤醒对应的挂起 future。
        if request.method == "approval/resolve":
            params = ApprovalResolveParams.model_validate(request.params)
            try:
                self._approvals.resolve(params)
            except KeyError as exc:
                raise RpcDispatchError("Unknown approval") from exc
            return {}, []

        # skills/list：列出 ~/.harness/skills 下 shared / personal 两个作用域的技能。
        if request.method == "skills/list":
            return {"skills": _list_skills(self._skills_root)}, []

        # skills/read：读取某个技能的 SKILL.md（路径会做越权校验）。
        if request.method == "skills/read":
            path = str(request.params.get("path", ""))
            file_path = _skill_disk_path(self._skills_root, path)
            if file_path is None or not file_path.is_file():
                raise RpcDispatchError("Unknown skill")
            return {"path": path, "content": file_path.read_text(encoding="utf-8")}, []

        # skills/write：写技能文件，且只允许写 personal 作用域。
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

        # config/get：读当前配置（api_key 已打码）。
        if request.method == "config/get":
            return {"config": self._public_config()}, []

        # config/set：改配置；若改了 model，就切换供应商并让 agent 缓存失效。
        if request.method == "config/set":
            params = ConfigSetParams.model_validate(request.params)
            self._config.update(params.values)
            if self._cfg is not None:
                self._cfg = self._cfg.model_copy(update=params.values)
            model = params.values.get("model")
            if isinstance(model, str) and model.strip():
                try:
                    self._providers_store().select(model)
                    invalidate_agents()
                    self._agent = None
                except KeyError:
                    pass
            return {"config": self._public_config()}, []

        # models/list：列出所有供应商及其模型，以及当前选中的模型。
        if request.method == "models/list":
            if self._cfg is not None:
                self._providers_store().seed_from_cfg(self._cfg)
            return self._providers_store().public(), []

        # models/set：切换当前模型/供应商，并让 agent 缓存失效以重建。
        if request.method == "models/set":
            params = ModelsSetParams.model_validate(request.params)
            try:
                self._providers_store().select(params.model, params.provider_id)
            except KeyError as exc:
                raise RpcDispatchError(exc.args[0] if exc.args else "Unknown model") from exc
            self._apply_providers()
            invalidate_agents()
            self._agent = None
            return self._providers_store().public(), []

        # providers/upsert：新增或更新一个供应商配置。
        if request.method == "providers/upsert":
            params = ProviderUpsertParams.model_validate(request.params)
            profile = self._providers_store().upsert(params.model_dump(mode="json"))
            self._apply_providers()
            invalidate_agents()
            self._agent = None
            return {"provider": profile.public(), **self._providers_store().public()}, []

        # providers/delete：删除供应商，并让 agent 缓存失效以重建。
        if request.method == "providers/delete":
            params = ProviderDeleteParams.model_validate(request.params)
            if not self._providers_store().delete(params.id):
                raise RpcDispatchError("Unknown provider")
            self._apply_providers()
            invalidate_agents()
            self._agent = None
            return self._providers_store().public(), []

        # 兜底：没有任何 action 匹配，返回 JSON-RPC 标准错误码 -32601（方法不存在）。
        raise RpcDispatchError(f"Unknown method: {request.method}", code=-32601)


# 把 "/skills/{scope}/..." 这类虚拟路径解析成磁盘路径，并挡住越权/目录穿越。
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


# 扫描 skills 根目录，收集 shared / personal 下每个 */SKILL.md。
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
