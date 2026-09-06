from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

WORDMARK = r"""
 ██╗  ██╗ █████╗ ██████╗ ███╗   ██╗███████╗███████╗███████╗
 ██║  ██║██╔══██╗██╔══██╗████╗  ██║██╔════╝██╔════╝██╔════╝
 ███████║███████║██████╔╝██╔██╗ ██║█████╗  ███████╗███████╗
 ██╔══██║██╔══██║██╔══██╗██║╚██╗██║██╔══╝  ╚════██║╚════██║
 ██║  ██║██║  ██║██║  ██║██║ ╚████║███████╗███████║███████║
 ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝╚══════╝
""".strip("\n")


def _pkg_version() -> str:
    try:
        return version("harness-agent")
    except PackageNotFoundError:
        return "0.1.0"


def render_banner(
    console: Console,
    *,
    workspace: str,
    host: str,
    port: int,
    thread_id: str,
    resumed: bool = False,
) -> None:
    mark = Text(WORDMARK, style="bold #E8A87C")
    tagline = Text("local coding agent  ·  App Server protocol", style="dim italic")
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("version", f"[#E8A87C]{_pkg_version()}[/]")
    meta.add_row("workspace", workspace)
    meta.add_row("server", f"ws://{host}:{port}")
    meta.add_row("thread", f"{thread_id}  [{'resume' if resumed else 'new'}]")
    hints = Text.from_markup(
        "[dim]type a task and press enter    [/][bold]/quit[/][dim] exit    [/][bold]/new[/][dim] new thread    [/][bold]/interrupt[/][dim] stop turn[/]"
    )
    body = Group(
        Align.center(mark),
        Text(),
        Align.center(tagline),
        Rule(style="#3D3A36"),
        Align.center(meta),
        Text(),
        Align.center(hints),
    )
    console.print()
    console.print(
        Panel(
            body,
            border_style="#6B5344",
            padding=(1, 2),
        )
    )
    console.print()
