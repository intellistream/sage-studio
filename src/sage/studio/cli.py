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
    """Lazy load StudioManager to avoid import issues."""
    global studio_manager
    if studio_manager is None:
        from sage.studio.studio_manager import StudioManager

        studio_manager = StudioManager()
    return studio_manager


@app.command()
def start(
    frontend_port: Optional[int] = typer.Option(
        None, "--port", "-p", help="Frontend port (default: 5173 dev, 8889 prod)"
    ),
    backend_port: Optional[int] = typer.Option(
        None, "--backend-port", help="Backend API port (default: 8080)"
    ),
    gateway_port: Optional[int] = typer.Option(
        None, "--gateway-port", help="Gateway port (default: 8000)"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    dev: bool = typer.Option(True, "--dev/--prod", help="Development or production mode"),
    llm: Optional[str] = typer.Option(None, "--llm", help="LLM service URL"),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="LLM model to use"
    ),
    embedding: Optional[str] = typer.Option(None, "--embedding", help="Embedding service URL"),
    embedding_model: Optional[str] = typer.Option(
        None, "--embedding-model", help="Embedding model to use"
    ),
    use_finetuned: bool = typer.Option(
        False, "--use-finetuned", help="Use finetuned model"
    ),
    interactive: Optional[bool] = typer.Option(
        None, "--interactive/--no-interactive", help="Interactive mode"
    ),
    skip_confirm: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts"
    ),
    no_embedding: bool = typer.Option(
        False, "--no-embedding", help="Skip embedding service"
    ),
):
    """Start SAGE Studio (frontend + backend)."""
    manager = _get_studio_manager()
    manager.start(
        frontend_port=frontend_port,
        backend_port=backend_port,
        gateway_port=gateway_port,
        host=host,
        dev=dev,
        llm=llm,
        llm_model=llm_model,
        embedding=embedding,
        embedding_model=embedding_model,
        use_finetuned=use_finetuned,
        interactive=interactive,
        skip_confirm=skip_confirm,
        no_embedding=no_embedding,
    )


@app.command()
def stop(
    stop_infrastructure: bool = typer.Option(
        False, "--stop-infra", help="Also stop gateway/LLM services"
    )
):
    """Stop SAGE Studio."""
    manager = _get_studio_manager()
    manager.stop(stop_infrastructure=stop_infrastructure)


@app.command()
def status():
    """Show Studio status."""
    manager = _get_studio_manager()
    status_info = manager.status()
    if status_info.get("running"):
        console.print("[green]✓ Studio is running[/green]")
        config = status_info.get("config", {})
        console.print(f"  Port: {config.get('port', 'N/A')}")
        console.print(f"  Host: {config.get('host', 'N/A')}")
    else:
        console.print("[yellow]Studio is not running[/yellow]")


@app.command()
def restart(
    frontend_port: Optional[int] = typer.Option(None, "--port", "-p", help="Frontend port"),
    dev: bool = typer.Option(True, "--dev/--prod", help="Development or production mode"),
):
    """Restart SAGE Studio."""
    manager = _get_studio_manager()
    console.print("🔄 Restarting Studio...")
    manager.stop(stop_infrastructure=False)
    manager.start(frontend_port=frontend_port, dev=dev, skip_confirm=True)


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
