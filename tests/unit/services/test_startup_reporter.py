from __future__ import annotations

from rich.console import Console

from sage.studio.supervisor import ServiceStatus, StartupReporter


def test_render_chat_ready() -> None:
    recorder = Console(record=True)
    reporter = StartupReporter(recorder)

    reporter.render_chat_ready(
        frontend_url="http://0.0.0.0:5173",
        services=[
            ServiceStatus(name="Gateway", port=8889, log_path="/tmp/gateway.log"),
            ServiceStatus(name="Studio 后端", port=8080, log_path="/tmp/backend.log"),
        ],
    )

    output = recorder.export_text()
    assert "Chat 模式就绪" in output
    assert "Gateway" in output
    assert "8080" in output
