"""
CodingAgent - L6 Wiring for CoderBot

Layer: L6 (sage-studio)

Thin wrapper: injects studio-specific FS tools and the gateway LLM callable
into the L3 CoderBot. Contains zero coding intelligence itself.

Pattern mirrors ResearcherAgent → SearcherBot.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sage_libs.sage_agentic.agents.bots.coder_bot import CoderBot

from sage.studio.models.agent_step import AgentStep
from sage.studio.services.agents.base import BaseAgent
from sage.studio.tools.base import BaseTool

logger = logging.getLogger(__name__)


class CodingAgent(BaseAgent):
    """
    L6 Coding Agent.

    Responsibilities:
    - Build a CoderBot with injected FS tools and gateway LLM callable.
    - Convert CoderBot event stream into AgentStep objects for the frontend.
    - Report workspace path on completion.

    Does NOT contain any coding intelligence (all in L3 CoderBot).
    """

    def __init__(self, tools: list[BaseTool], llm_callable: Any):
        super().__init__(name="Coder", role="Software Engineer", tools=tools)
        self.bot = CoderBot(tools=list(tools), llm_callable=llm_callable)

    async def run(self, query: str, history: list[dict] | None = None) -> AsyncGenerator[AgentStep, None]:
        """Delegate to CoderBot and translate events to AgentSteps."""
        yield AgentStep.create(
            type="reasoning",
            content=f"Coder Agent 接收任务: {query}",
            status="running",
        )

        async for event in self.bot.execute_stream(query):
            event_type = event.get("type", "")

            if event_type == "plan_start":
                yield AgentStep.create(
                    type="reasoning",
                    content="正在规划项目结构...",
                    status="running",
                )

            elif event_type == "plan":
                plan = event["plan"]
                files = plan.get("files", [])
                file_list = "\n".join(f"  • {f['path']}" for f in files[:20])
                yield AgentStep.create(
                    type="reasoning",
                    content=(
                        f"项目规划完成: **{plan.get('project_name', 'app')}**\n"
                        f"技术栈: {', '.join(plan.get('tech_stack', []))}\n"
                        f"共 {len(files)} 个文件:\n{file_list}"
                    ),
                    status="completed",
                    metadata={"plan": plan},
                )

            elif event_type == "plan_error":
                yield AgentStep.create(
                    type="reasoning",
                    content=f"规划失败: {event['error']}",
                    status="failed",
                )
                return

            elif event_type == "file_start":
                yield AgentStep.create(
                    type="tool_call",
                    content=f"[{event['index'] + 1}/{event['total']}] 生成: {event['path']}",
                    status="running",
                    tool_name="llm_generate",
                )

            elif event_type == "file_ready":
                yield AgentStep.create(
                    type="tool_result",
                    content=f"已生成 {event['path']} ({event['bytes']} bytes)",
                    status="completed",
                )

            elif event_type == "tool_start":
                yield AgentStep.create(
                    type="tool_call",
                    content=f"写入文件: {event['path']}",
                    status="running",
                    tool_name=event["tool"],
                )

            elif event_type == "tool_result":
                result = event.get("result", {})
                if result.get("status") == "success":
                    yield AgentStep.create(
                        type="tool_result",
                        content=f"✓ {event['path']}",
                        status="completed",
                    )
                else:
                    yield AgentStep.create(
                        type="tool_result",
                        content=f"✗ {event['path']}: {result.get('error', 'unknown error')}",
                        status="failed",
                    )

            elif event_type == "done":
                project = event.get("project_name", "app")
                n = event.get("files_written", 0)
                yield AgentStep.create(
                    type="reasoning",
                    content=(
                        f"项目 **{project}** 生成完成，共写入 {n} 个文件。\n"
                        f"工作区路径: `~/sage_studio_projects/{project}/`"
                    ),
                    status="completed",
                )
                # Emit summary text so it appears in the chat bubble
                yield f"项目 **{project}** 已生成 ✓  （{n} 个文件写入 `~/sage_studio_projects/{project}/`）"

            elif event_type == "error":
                yield AgentStep.create(
                    type="reasoning",
                    content=f"错误: {event['error']}",
                    status="failed",
                )
