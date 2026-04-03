#!/usr/bin/env python3
"""SAGE Studio CLI - Visual workflow builder.

Studio provides a modern web UI for:
- Visual pipeline development with drag-and-drop
- Properties panel for configuration
- Session management and persistence
"""

from __future__ import annotations

import argparse

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="🎨 Studio - Visual workflow builder")

# Lazy import to avoid circular dependencies
studio_manager = None


def _get_studio_manager():
    """Lazy load StudioManager to avoid importing heavy runtime dependencies eagerly."""
    global studio_manager
    if studio_manager is None:
        from sage.studio.studio_manager import StudioManager

        studio_manager = StudioManager()
    return studio_manager


@app.command()
def start(
    frontend_port: int | None = typer.Option(
        None, "--port", "-p", help="Frontend port (default: 5173 dev, 8889 prod)"
    ),
    backend_port: int | None = typer.Option(
        None, "--backend-port", help="Backend API port (default: 8080)"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    dev: bool = typer.Option(True, "--dev/--prod", help="Development or production mode"),
    skip_confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
):
    """Start SAGE Studio (frontend + backend)."""
    manager = _get_studio_manager()
    manager.start(
        port=frontend_port,
        backend_port=backend_port,
        host=host,
        dev=dev,
        skip_confirm=skip_confirm,
    )


@app.command()
def stop(
    stop_gateway: bool = typer.Option(False, "--stop-gateway", help="Also stop gateway service"),
    stop_llm: bool = typer.Option(False, "--stop-llm", help="Also stop LLM service"),
    stop_all: bool = typer.Option(False, "--all", help="Stop all services (gateway + LLM)"),
):
    """Stop SAGE Studio."""
    manager = _get_studio_manager()
    if stop_all:
        manager.stop(stop_gateway=True, stop_llm=True)
    else:
        manager.stop(stop_gateway=stop_gateway, stop_llm=stop_llm)


@app.command()
def status():
    """Show Studio status."""
    manager = _get_studio_manager()
    try:
        manager.status()
    except Exception as exc:
        console.print(f"[red]❌ Error getting Studio status: {exc}[/red]")


@app.command()
def restart(
    frontend_port: int | None = typer.Option(None, "--port", "-p", help="Frontend port"),
    dev: bool = typer.Option(True, "--dev/--prod", help="Development or production mode"),
    skip_confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
):
    """Restart SAGE Studio."""
    manager = _get_studio_manager()
    console.print("🔄 Restarting Studio...")
    # 🔧 FIX: 重启时停止 LLM 服务（避免端口冲突），但保留 Gateway（共享服务）
    manager.stop(stop_gateway=False, stop_llm=True)
    manager.start(port=frontend_port, dev=dev, skip_confirm=skip_confirm)


@app.command()
def logs(
    backend: bool = typer.Option(False, "--backend", help="Show backend logs"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
):
    """Show Studio logs."""
    manager = _get_studio_manager()
    manager.logs(backend=backend, follow=follow)


@app.command()
def open():
    """Open Studio in default browser."""
    manager = _get_studio_manager()
    manager.open_browser()


@app.command()
def install():
    """Install frontend dependencies."""
    manager = _get_studio_manager()
    manager.install()


@app.command()
def build():
    """Build frontend for production."""
    manager = _get_studio_manager()
    manager.build()


@app.command()
def clean():
    """Clean build artifacts and caches."""
    manager = _get_studio_manager()
    manager.clean()


@app.command()
def npm(
    args: list[str] = typer.Argument(..., help="npm command and arguments"),
):
    """Run npm command in frontend directory."""
    manager = _get_studio_manager()
    manager.run_npm_command(args)


def _run_studio_argparse(args: argparse.Namespace) -> int:
    """Dispatch argparse-captured studio args to the Typer app."""
    studio_args = list(args.studio_args or [])
    if studio_args and studio_args[0] == "--":
        studio_args = studio_args[1:]

    try:
        app(args=studio_args, prog_name="sage studio", standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code)

    return 0


# For SAGE CLI integration
def register_studio_command(sage_cli: object) -> None:
    """Register studio commands to SAGE CLI app.

    Supports both:
    - Typer root app (``add_typer``)
    - argparse subparsers action (``add_parser``)
    """
    if hasattr(sage_cli, "add_typer"):
        sage_cli.add_typer(app, name="studio")
        return

    if hasattr(sage_cli, "add_parser"):
        parser = sage_cli.add_parser(
            "studio",
            help="Studio visual workflow builder",
            add_help=False,
        )
        parser.add_argument(
            "studio_args",
            nargs=argparse.REMAINDER,
            help="Arguments passed through to 'sage studio'",
        )
        parser.set_defaults(_handler=_run_studio_argparse)
        return

    raise TypeError(
        "Unsupported SAGE CLI object for studio registration; expected Typer app or argparse subparsers"
    )
