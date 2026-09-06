from __future__ import annotations

import asyncio
import os

import typer

from config.load import load_harness_config

app = typer.Typer(add_completion=False, invoke_without_command=True, no_args_is_help=False)


def _ws(cfg=None) -> tuple[str, int]:
    cfg = cfg or load_harness_config()
    return cfg.ws_bind or "127.0.0.1", int(cfg.ws_port or 8765)


@app.callback()
def _root(
    ctx: typer.Context,
    workspace: str = typer.Option(os.getcwd(), "--workspace", help="Workspace path"),
    new: bool = typer.Option(False, "--new", help="Start a new thread instead of resuming"),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["workspace"] = workspace
    ctx.obj["new"] = new
    if ctx.invoked_subcommand is None:
        from harness_cli.tui import run_tui

        host, port = _ws()
        asyncio.run(run_tui(workspace, force_new=new, host=host, port=port))


@app.command()
def ask(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="User prompt"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Dev only: approve HITL"),
) -> None:
    from harness_cli.tui import run_ask

    workspace = ctx.obj["workspace"]
    host, port = _ws()
    asyncio.run(
        run_ask(
            workspace,
            text,
            auto_approve=auto_approve,
            force_new=ctx.obj.get("new", False),
            host=host,
            port=port,
        )
    )


@app.command()
def resume(
    ctx: typer.Context,
    thread_id: str = typer.Argument(..., help="Thread id"),
) -> None:
    from harness_cli.tui import run_tui

    workspace = ctx.obj["workspace"]
    host, port = _ws()
    asyncio.run(run_tui(workspace, thread_id=thread_id, host=host, port=port))


@app.command()
def serve(
    host: str = typer.Option(None),
    port: int = typer.Option(None),
) -> None:
    from server.app import run_server

    cfg = load_harness_config()
    bind = host or cfg.ws_bind or "127.0.0.1"
    ws_port = port or cfg.ws_port or 8765
    asyncio.run(run_server(bind, ws_port))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
