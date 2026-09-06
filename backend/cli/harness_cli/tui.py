from __future__ import annotations

import asyncio
import time

from protocol.events import ItemEvent, ItemType
from protocol.frame import RpcNotification, RpcResponse
from protocol.methods import (
    ApprovalDecision,
    ApprovalResolveParams,
    ClientType,
    InitializeParams,
    ThreadResumeParams,
    ThreadStartParams,
    TurnInterruptParams,
    TurnStartParams,
)
from rich.console import Console
from rich.rule import Rule

from harness_cli.banner import render_banner
from harness_cli.client import HarnessClient


def _divider(console: Console, title: str = "") -> None:
    console.print(Rule(title, style="dim") if title else Rule(style="dim"))


def _tool_line(event: ItemEvent, *, done: bool) -> str:
    mark = "✓" if done else "●"
    label = event.tool or event.type.value
    detail = event.path or event.text or ""
    if detail and len(detail) > 80:
        detail = detail[:77] + "..."
    color = "green" if done else "cyan"
    extra = f" [dim]{detail}[/]" if detail else ""
    return f"[{color}]{mark} {label}[/]{extra}"


class TurnView:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.started = time.monotonic()
        self._answer = False
        self._seen: set[str] = set()
        self._status = console.status("[#E8A87C]thinking[/] [dim]0.0s[/]", spinner="dots")

    def start(self) -> None:
        self._status.start()

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def _stop_spinner(self) -> None:
        self._status.stop()

    def render(self, msg) -> None:
        if isinstance(msg, RpcResponse):
            return
        if not isinstance(msg, RpcNotification):
            return
        if msg.method == "approval/request":
            self._stop_spinner()
            self.console.print(f"[yellow]approval[/] {msg.params.get('tool')} {msg.params.get('args')}")
            return
        if msg.method == "error":
            self.console.print(f"[red]error[/] {msg.params.get('message')}")
            return
        if msg.method == "turn/completed":
            status = msg.params.get("status")
            self._stop_spinner()
            self.console.print()
            label = f"{self.elapsed():.1f}s"
            if status:
                label = f"{label} {status}"
            _divider(self.console, label)
            return
        if msg.method not in {"item/started", "item/delta", "item/completed"}:
            return
        event = ItemEvent.model_validate(msg.params)
        if event.type == ItemType.REASONING and event.text:
            snippet = event.text.replace("\n", " ").strip()
            if len(snippet) > 90:
                snippet = snippet[:87] + "..."
            self.console.print(f"[dim italic]  {snippet}[/]")
            return
        if event.type != ItemType.AGENT_MESSAGE:
            key = f"{msg.method}:{event.item_id}:{event.tool}"
            if key in self._seen:
                return
            self._seen.add(key)
            if msg.method == "item/started":
                self.console.print(_tool_line(event, done=False))
            elif msg.method == "item/completed":
                self.console.print(_tool_line(event, done=True))
            return
        if msg.method == "item/delta" and event.text:
            if not self._answer:
                self._stop_spinner()
                self.console.print()
                self._answer = True
            self.console.print(event.text, end="")


def _ask_approval(console: Console, params: dict, *, auto_approve: bool) -> dict:
    request_id = str(params.get("request_id") or "")
    if auto_approve:
        return ApprovalResolveParams(
            request_id=request_id, decision=ApprovalDecision.APPROVE
        ).model_dump(mode="json")
    allowed = params.get("allowed_decisions") or ["approve", "reject"]
    raw = console.input(f"approval {allowed} [a/r/e]: ").strip().lower()
    decision = {
        "a": ApprovalDecision.APPROVE,
        "approve": ApprovalDecision.APPROVE,
        "r": ApprovalDecision.REJECT,
        "reject": ApprovalDecision.REJECT,
        "e": ApprovalDecision.EDIT,
        "edit": ApprovalDecision.EDIT,
    }.get(raw, ApprovalDecision.REJECT)
    edited = None
    if decision == ApprovalDecision.EDIT:
        edited_raw = console.input("edited args json (empty skip): ").strip()
        if edited_raw:
            import json

            edited = json.loads(edited_raw)
    return ApprovalResolveParams(
        request_id=request_id, decision=decision, edited_args=edited
    ).model_dump(mode="json")


async def run_session(
    workspace: str,
    *,
    thread_id: str | None = None,
    prompt: str | None = None,
    auto_approve: bool = False,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    console = Console()
    client = HarnessClient(host, port)
    await client.connect()
    try:
        await client.request(
            "initialize",
            InitializeParams(client=ClientType.CLI, cwd=workspace).model_dump(mode="json"),
        )
        if thread_id:
            info, _ = await client.request(
                "thread/resume",
                ThreadResumeParams(thread_id=thread_id).model_dump(mode="json"),
            )
        else:
            info, _ = await client.request(
                "thread/start",
                ThreadStartParams(workspace=workspace).model_dump(mode="json"),
            )
        tid = info["thread_id"]
        if prompt is None:
            render_banner(
                console,
                workspace=workspace,
                host=host,
                port=port,
                thread_id=tid,
                resumed=thread_id is not None,
            )

        async def _run_turn(text: str) -> None:
            _divider(console)
            view = TurnView(console)
            view.start()
            stop = asyncio.Event()

            async def _tick() -> None:
                while not stop.is_set():
                    view._status.update(f"[#E8A87C]thinking[/] [dim]{view.elapsed():.1f}s[/]")
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=0.2)
                    except TimeoutError:
                        pass

            ticker = asyncio.create_task(_tick())
            try:
                async for msg in client.request_iter(
                    "turn/start",
                    TurnStartParams(thread_id=tid, text=text).model_dump(mode="json"),
                ):
                    view.render(msg)
                    if isinstance(msg, RpcNotification) and msg.method == "approval/request":
                        resolve = _ask_approval(console, msg.params, auto_approve=auto_approve)
                        await client.send_request("approval/resolve", resolve)
            finally:
                stop.set()
                ticker.cancel()
                view._stop_spinner()

        if prompt is not None:
            console.print(f"[bold]>[/] {prompt}")
            await _run_turn(prompt)
            return

        while True:
            try:
                text = (await asyncio.to_thread(console.input, "[bold]>[/] ")).strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                return
            if not text:
                continue
            if text in {":q", "/quit", "/exit"}:
                return
            if text in {"/interrupt", ":interrupt"}:
                await client.request(
                    "turn/interrupt",
                    TurnInterruptParams(thread_id=tid).model_dump(mode="json"),
                )
                continue
            await _run_turn(text)
    finally:
        await client.close()


async def run_tui(workspace: str, thread_id: str | None = None, **kwargs) -> None:
    await run_session(workspace, thread_id=thread_id, **kwargs)


async def run_ask(workspace: str, text: str, *, auto_approve: bool = False, **kwargs) -> None:
    await run_session(workspace, prompt=text, auto_approve=auto_approve, **kwargs)
