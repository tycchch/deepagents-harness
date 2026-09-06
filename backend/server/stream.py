from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from protocol.events import ApprovalRequestParams, ItemEvent, ItemType
from protocol.frame import RpcNotification
from protocol.methods import ApprovalResolveParams


class ApprovalHub:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ApprovalResolveParams]] = {}

    def request(self, params: ApprovalRequestParams) -> asyncio.Future[ApprovalResolveParams]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalResolveParams] = loop.create_future()
        self._pending[params.request_id] = future
        return future

    def resolve(self, params: ApprovalResolveParams) -> None:
        future = self._pending.pop(params.request_id, None)
        if future is None:
            raise KeyError(params.request_id)
        if not future.done():
            future.set_result(params)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


def _reasoning_text(message: object) -> str:
    content = getattr(message, "content", "")
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in {"reasoning", "thinking"}:
                parts.append(
                    str(block.get("thinking") or block.get("text") or block.get("reasoning") or "")
                )
    extra = getattr(message, "additional_kwargs", None) or {}
    if isinstance(extra, dict):
        reasoning = extra.get("reasoning")
        if isinstance(reasoning, str):
            parts.append(reasoning)
        elif isinstance(reasoning, dict):
            parts.append(str(reasoning.get("content") or reasoning.get("text") or ""))
    return "".join(parts)


def _tool_calls(message: object) -> list[dict]:
    found: list[dict] = []
    for call in getattr(message, "tool_calls", None) or []:
        if isinstance(call, dict):
            name = str(call.get("name") or "")
            if name:
                found.append(call)
        else:
            name = str(getattr(call, "name", "") or "")
            if name:
                found.append(
                    {
                        "name": name,
                        "args": getattr(call, "args", {}) or {},
                        "id": getattr(call, "id", "") or "",
                    }
                )
    if found:
        return found
    for chunk in getattr(message, "tool_call_chunks", None) or []:
        if isinstance(chunk, dict):
            name = str(chunk.get("name") or "")
            if not name:
                continue
            found.append(
                {
                    "name": name,
                    "args": chunk.get("args") or {},
                    "id": chunk.get("id") or "",
                }
            )
    return found


def _tool_item_type(name: str) -> ItemType:
    if name in {"execute", "shell"}:
        return ItemType.COMMAND_EXECUTION
    if name in {"write_file", "edit_file"}:
        return ItemType.FILE_CHANGE
    if name in {"read_skill", "skill"}:
        return ItemType.SKILL_USE
    return ItemType.TOOL_CALL


def _tool_detail(args: object) -> tuple[str | None, str | None]:
    if not isinstance(args, dict):
        return None, None
    path = args.get("path") or args.get("file_path")
    text = args.get("command") or args.get("cmd") or args.get("query")
    return (str(path) if path else None), (str(text) if text else None)


def map_stream_event(mode: str, payload: object) -> list[RpcNotification]:
    if mode != "messages":
        return []
    message = payload[0] if isinstance(payload, tuple) else payload
    name = getattr(message, "name", "") or ""
    text = _content_text(getattr(message, "content", ""))
    type_name = type(message).__name__
    notes: list[RpcNotification] = []
    if "Tool" in type_name:
        item_type = _tool_item_type(name)
        event = ItemEvent(
            item_id=str(getattr(message, "tool_call_id", "tool") or "tool"),
            type=item_type,
            text=text or None,
            tool=name or None,
        )
        return [RpcNotification(method="item/completed", params=event.model_dump(mode="json"))]
    for call in _tool_calls(message):
        tool_name = str(call.get("name") or "")
        path, detail = _tool_detail(call.get("args"))
        event = ItemEvent(
            item_id=str(call.get("id") or tool_name or "tool"),
            type=_tool_item_type(tool_name),
            text=detail,
            tool=tool_name or None,
            path=path,
        )
        notes.append(RpcNotification(method="item/started", params=event.model_dump(mode="json")))
    reasoning = _reasoning_text(message)
    if reasoning:
        event = ItemEvent(item_id="think", type=ItemType.REASONING, text=reasoning)
        notes.append(RpcNotification(method="item/delta", params=event.model_dump(mode="json")))
    if text:
        event = ItemEvent(item_id="msg", type=ItemType.AGENT_MESSAGE, text=text)
        notes.append(RpcNotification(method="item/delta", params=event.model_dump(mode="json")))
    return notes


class AgentTurnStreamer:
    def __init__(self, agent) -> None:
        self._agent = agent

    async def run(self, text: str, thread_id: str = "") -> AsyncIterator[RpcNotification]:
        started = False
        config = {"configurable": {"thread_id": thread_id or "default"}}
        yield RpcNotification(method="turn/started", params={"thread_id": thread_id})
        stream = self._agent.astream(
            {"messages": [{"role": "user", "content": text}]},
            config=config,
            stream_mode=["messages"],
        )
        async for item in stream:
            if isinstance(item, tuple) and item and item[0] in {"messages", "updates"}:
                mode, payload = item[0], item[1]
            else:
                mode, payload = "messages", item
            for note in map_stream_event(mode, payload):
                if note.method == "item/delta" and not started:
                    yield RpcNotification(method="item/started", params={**note.params, "text": None})
                    started = True
                yield note
        yield RpcNotification(method="turn/completed", params={})


def _agent_notes(text: str) -> list[RpcNotification]:
    item = ItemEvent(item_id="item-1", type=ItemType.AGENT_MESSAGE, text=f"echo: {text}")
    payload = item.model_dump(mode="json")
    return [
        RpcNotification(method="item/started", params={**payload, "text": None}),
        RpcNotification(method="item/delta", params=payload),
        RpcNotification(method="item/completed", params=payload),
        RpcNotification(method="turn/completed", params={}),
    ]


class FakeTurnStreamer:
    def __init__(self, delay_s: float = 0) -> None:
        self.delay_s = delay_s

    def sync_events(self, text: str) -> list[RpcNotification]:
        return _agent_notes(text)

    async def run(self, text: str, thread_id: str = "") -> AsyncIterator[RpcNotification]:
        del thread_id
        notes = _agent_notes(text)
        yield notes[0]
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        for note in notes[1:]:
            yield note


class TurnRunner:
    def __init__(self, streamer: FakeTurnStreamer | AgentTurnStreamer | None = None) -> None:
        self._streamer = streamer or FakeTurnStreamer()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def is_busy(self, thread_id: str) -> bool:
        task = self._tasks.get(thread_id)
        return task is not None and not task.done()

    def interrupt(self, thread_id: str) -> bool:
        task = self._tasks.get(thread_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def stream(self, thread_id: str, text: str) -> AsyncIterator[RpcNotification]:
        if self.is_busy(thread_id):
            raise RuntimeError("Turn already running")

        queue: asyncio.Queue[RpcNotification | None] = asyncio.Queue()

        async def _run() -> None:
            try:
                async for note in self._streamer.run(text, thread_id=thread_id):
                    await queue.put(note)
            except asyncio.CancelledError:
                await queue.put(RpcNotification(method="turn/completed", params={"status": "interrupted"}))
            except Exception as exc:
                await queue.put(
                    RpcNotification(method="error", params={"code": -32000, "message": str(exc)})
                )
                await queue.put(RpcNotification(method="turn/completed", params={"status": "error"}))
            finally:
                await queue.put(None)

        task = asyncio.create_task(_run())
        self._tasks[thread_id] = task
        try:
            while True:
                note = await queue.get()
                if note is None:
                    break
                yield note
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._tasks.pop(thread_id, None)

    async def start(self, thread_id: str, text: str) -> list[RpcNotification]:
        return [note async for note in self.stream(thread_id, text)]
