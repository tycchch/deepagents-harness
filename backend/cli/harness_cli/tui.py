from __future__ import annotations

import asyncio
import time
from pathlib import Path

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

from config.providers import parse_model_spec
from harness_cli.banner import render_banner
from harness_cli.client import HarnessClient, HarnessRpcError

# Session slash commands. Add a row here, then handle it in run_session().
COMMANDS: list[tuple[str, str]] = [
    ("/help", "列出全部命令"),
    ("/quit", "退出 TUI（:q / /exit 同义）"),
    ("/new", "开一条新的 CLI 会话"),
    ("/interrupt", "中断当前 turn"),
    ("/model", "列出供应商与模型"),
    ("/model <alias|id>", "按别名或模型 id 切换，如 /model sonnet"),
    ("/model <provider>/<id>", "指定供应商切换，如 /model deepseek/opus"),
]


def print_help(console: Console) -> None:
    console.print("[bold]commands[/]")
    for name, hint in COMMANDS:
        console.print(f"  [bold]{name:<28}[/][dim]{hint}[/]")


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


async def _print_history(console: Console, client: HarnessClient, thread_id: str) -> None:
    try:
        result, _ = await client.request("thread/history", {"thread_id": thread_id})
    except HarnessRpcError:
        return
    items = result.get("items") or []
    if not items:
        return
    _divider(console, "history")
    for raw in items:
        event = ItemEvent.model_validate(raw)
        if event.type == ItemType.USER_MESSAGE:
            console.print(f"[bold]>[/] {event.text or ''}")
        elif event.type == ItemType.AGENT_MESSAGE:
            console.print(event.text or "")
        elif event.type == ItemType.REASONING:
            snippet = (event.text or "").replace("\n", " ").strip()
            if len(snippet) > 90:
                snippet = snippet[:87] + "..."
            console.print(f"[dim italic]  {snippet}[/]")
        else:
            console.print(_tool_line(event, done=True))


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


async def _handle_model_cmd(console: Console, client: HarnessClient, text: str) -> None:
    spec = text.split(maxsplit=1)
    try:
        listed, _ = await client.request("models/list", {})
    except HarnessRpcError as exc:
        console.print(f"[red]model[/] {exc.message}")
        return
    providers = listed.get("providers") or []
    if len(spec) < 2:
        current = f"{listed.get('active_provider') or '-'} / {listed.get('active_model') or '-'}"
        console.print(f"[dim]current[/] {current}")
        if not providers:
            console.print("[dim]no providers. add one in Settings.[/]")
            return
        for item in providers:
            mark = "*" if item.get("id") == listed.get("active_provider") else " "
            aliases = ", ".join(f"{k}={v}" for k, v in (item.get("mapping") or {}).items())
            models = ", ".join(m.get("id") or "" for m in (item.get("models") or []))
            extra = f"  [dim]{aliases}[/]" if aliases else ""
            console.print(f" {mark} [bold]{item.get('name')}[/] ({item.get('protocol')}) {models}{extra}")
        console.print("[dim]/model <alias|id>   /model <provider>/<id>[/]")
        return
    provider_id, model = parse_model_spec(spec[1])
    try:
        result, _ = await client.request(
            "models/set",
            {"model": model, "provider_id": provider_id},
        )
    except HarnessRpcError as exc:
        console.print(f"[red]model[/] {exc.message}")
        return
    console.print(f"[green]model[/] {result.get('active_provider')} / {result.get('active_model')}")


def _same_workspace(left: str, right: str) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except OSError:
        return left.rstrip("\\/") == right.rstrip("\\/")


async def _open_thread(
    client: HarnessClient,
    workspace: str,
    *,
    thread_id: str | None,
    force_new: bool,
) -> tuple[dict, bool]:
    if thread_id:
        info, _ = await client.request(
            "thread/resume",
            ThreadResumeParams(thread_id=thread_id).model_dump(mode="json"),
        )
        return info, True
    if not force_new:
        listed, _ = await client.request("thread/list", {})
        threads = listed.get("threads") or []
        match = next((item for item in threads if _same_workspace(str(item.get("workspace") or ""), workspace)), None)
        if match:
            try:
                info, _ = await client.request(
                    "thread/resume",
                    ThreadResumeParams(thread_id=str(match["thread_id"])).model_dump(mode="json"),
                )
                return info, True
            except HarnessRpcError:
                pass
    info, _ = await client.request(
        "thread/start",
        ThreadStartParams(workspace=workspace).model_dump(mode="json"),
    )
    return info, False

# TUI 会话入口
async def run_session(
    workspace: str,
    *,
    thread_id: str | None = None,
    prompt: str | None = None,
    auto_approve: bool = False,
    force_new: bool = False,
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
        info, resumed = await _open_thread(
            client, workspace, thread_id=thread_id, force_new=force_new
        )
        tid = info["thread_id"]
        if prompt is None:
            render_banner(
                console,
                workspace=workspace,
                host=host,
                port=port,
                thread_id=tid,
                resumed=resumed,
            )
            if resumed:
                await _print_history(console, client, tid)

        # 发送请求，等待服务端响应，收到响应后渲染到控制台
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
            if text in {"/help", ":help", "/?"}:
                print_help(console)
                continue
            if text in {":q", "/quit", "/exit"}:
                return
            if text in {"/new", ":new"}:
                info, _ = await client.request(
                    "thread/start",
                    ThreadStartParams(workspace=workspace).model_dump(mode="json"),
                )
                tid = info["thread_id"]
                console.print(f"[dim]new thread {tid}[/]")
                continue
            if text in {"/interrupt", ":interrupt"}:
                await client.request(
                    "turn/interrupt",
                    TurnInterruptParams(thread_id=tid).model_dump(mode="json"),
                )
                continue
            if text == "/model" or text.startswith("/model ") or text.startswith(":model"):
                await _handle_model_cmd(console, client, text)
                continue
            await _run_turn(text)
    finally:
        await client.close()


async def run_tui(workspace: str, thread_id: str | None = None, **kwargs) -> None:
    await run_session(workspace, thread_id=thread_id, **kwargs)


async def run_ask(workspace: str, text: str, *, auto_approve: bool = False, **kwargs) -> None:
    await run_session(workspace, prompt=text, auto_approve=auto_approve, **kwargs)
