#!/usr/bin/env python3
"""SAGE Studio CLI - Visual workflow builder and LLM playground.

Studio provides a modern web UI for:
- Visual pipeline development with drag-and-drop
- Real-time chat playground with LLM testing
- Properties panel for configuration
- Session management and persistence
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="🎨 Studio - Visual workflow builder")

# Lazy import to avoid circular dependencies
studio_manager = None


def _get_studio_manager():
    """Lazy load ChatModeManager (default manager with full LLM support)."""
    global studio_manager
    if studio_manager is None:
        from sage.studio.chat_manager import ChatModeManager

        studio_manager = ChatModeManager()
    return studio_manager


@app.command()
def start(
    frontend_port: Optional[int] = typer.Option(
        None, "--port", "-p", help="Frontend port (default: 5173 dev, 8889 prod)"
    ),
    backend_port: Optional[int] = typer.Option(
        None, "--backend-port", help="Backend API port (default: 8080)"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    dev: bool = typer.Option(True, "--dev/--prod", help="Development or production mode"),
    skip_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts"
    ),
):
    """Start SAGE Studio (frontend + backend)."""
    manager = _get_studio_manager()
    manager.start(
        frontend_port=frontend_port,
        backend_port=backend_port,
        host=host,
        dev=dev,
        skip_confirm=skip_confirm,
    )


@app.command()
def stop(
    stop_gateway: bool = typer.Option(
        False, "--stop-gateway", help="Also stop gateway service"
    ),
    stop_llm: bool = typer.Option(
        False, "--stop-llm", help="Also stop LLM service"
    ),
    stop_all: bool = typer.Option(
        False, "--all", help="Stop all services (gateway + LLM)"
    )
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
    frontend_port: Optional[int] = typer.Option(None, "--port", "-p", help="Frontend port"),
    dev: bool = typer.Option(True, "--dev/--prod", help="Development or production mode"),
    skip_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts"
    ),
):
    """Restart SAGE Studio."""
    manager = _get_studio_manager()
    console.print("🔄 Restarting Studio...")
    # 🔧 FIX: 重启时停止 LLM 服务（避免端口冲突），但保留 Gateway（共享服务）
    manager.stop(stop_gateway=False, stop_llm=True)
    manager.start(frontend_port=frontend_port, dev=dev, skip_confirm=skip_confirm)


@app.command()
def logs(
    backend: bool = typer.Option(False, "--backend", help="Show backend logs"),
    gateway: bool = typer.Option(False, "--gateway", help="Show gateway logs"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
):
    """Show Studio logs."""
    manager = _get_studio_manager()
    manager.logs(backend=backend, gateway=gateway, follow=follow, lines=lines)


@app.command()
def open():
    """Open Studio in default browser."""
    manager = _get_studio_manager()
    manager.open()


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


# For SAGE CLI integration
def register_studio_command(sage_app: typer.Typer) -> None:
    """Register studio commands to SAGE CLI app.

    This function is called by SAGE CLI to dynamically add studio commands.
    """
    sage_app.add_typer(app, name="studio")
