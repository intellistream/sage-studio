from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console


@dataclass(slots=True)
class ServiceStatus:
    name: str
    port: int
    log_path: str


class StartupReporter:
    """Print unified startup summary panel in workflow order."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def render_chat_ready(self, frontend_url: str, services: list[ServiceStatus]) -> None:
        self.console.print("=" * 70)
        self.console.print("🎉 Chat 模式就绪！")
        self.console.print("=" * 70)
        self.console.print(f"🎨 Studio 前端: {frontend_url}")
        self.console.print("💬 打开顶部 Chat 标签即可体验")
        self.console.print()
        self.console.print("📡 运行中的服务：")
        for item in services:
            self.console.print(
                f"   {item.name:<12} | 端口: [yellow]{item.port}[/yellow]"
                f"  | 日志: [dim]{item.log_path}[/dim]"
            )
        self.console.print("=" * 70)
