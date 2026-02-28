from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    """记忆项"""

    id: str
    content: str
    type: str  # "short_term", "long_term"
    metadata: dict[str, Any]
    relevance: float = 0.0


class MemoryIntegrationService:
    """记忆集成服务

    使用 NeuroMem UnifiedCollection 提供记忆存储和检索。
    每个 session 拥有两个 collection：短期记忆 (STM) 和长期记忆 (LTM)。
    使用 BM25 索引实现文本检索（无需 embedding 模型）。
    """

    _INDEX_NAME = "bm25"

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._init_memory_backend()

    def _init_memory_backend(self):
        """初始化 NeuroMem 后端"""
        try:
            from neuromem.memory_collection.unified_collection import (
                UnifiedCollection,
            )

            stm_name = f"studio_stm_{self.session_id}"
            ltm_name = f"studio_ltm_{self.session_id}"

            self.short_term = UnifiedCollection(stm_name, storage_backend="memory")
            self.long_term = UnifiedCollection(ltm_name, storage_backend="memory")

            # 添加 BM25 索引用于文本检索
            self.short_term.add_index(self._INDEX_NAME, "bm25")
            self.long_term.add_index(self._INDEX_NAME, "bm25")

            self._available = True
            logger.info("NeuroMem initialized for session %s", self.session_id)

        except ImportError as exc:
            logger.info(
                "NeuroMem not available (%s), using in-memory fallback. "
                "Session memory works but is not persistent across restarts.",
                exc,
            )
            self._available = False
            self._fallback_memory: list[MemoryItem] = []
        except Exception as exc:
            logger.warning("NeuroMem init failed (%s), using fallback.", exc)
            self._available = False
            self._fallback_memory: list[MemoryItem] = []

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def add_interaction(
        self,
        user_message: str,
        assistant_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加交互到短期记忆"""
        metadata = metadata or {}
        content = f"User: {user_message}\nAssistant: {assistant_response}"

        if self._available:
            self.short_term.insert(
                text=content,
                metadata={"type": "interaction", **metadata},
                index_names=[self._INDEX_NAME],
            )
        else:
            self._fallback_memory.append(
                MemoryItem(
                    id=f"mem_{len(self._fallback_memory)}",
                    content=content,
                    type="short_term",
                    metadata=metadata,
                )
            )

    async def add_knowledge(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加知识到长期记忆"""
        metadata = metadata or {}

        if self._available:
            self.long_term.insert(
                text=content,
                metadata={"type": "knowledge", **metadata},
                index_names=[self._INDEX_NAME],
            )
        else:
            self._fallback_memory.append(
                MemoryItem(
                    id=f"mem_{len(self._fallback_memory)}",
                    content=content,
                    type="long_term",
                    metadata=metadata,
                )
            )

    async def add_evidence_batch(
        self,
        items: list[MemoryItem] | list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store retrieved evidence into long-term memory for future recall."""
        meta = metadata or {}
        for item in items:
            if isinstance(item, MemoryItem):
                await self.add_knowledge(item.content, {"evidence": True, **meta})
            else:
                content = item.get("content")
                if content:
                    await self.add_knowledge(content, {"evidence": True, **meta})

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def retrieve_context(
        self,
        query: str,
        max_items: int = 5,
    ) -> list[MemoryItem]:
        """检索相关上下文"""
        results: list[MemoryItem] = []

        if self._available:
            half = max(max_items // 2, 1)

            # 短期记忆检索
            try:
                stm_results = self.short_term.retrieve(
                    self._INDEX_NAME, query, top_k=half,
                )
                for item in stm_results:
                    results.append(
                        MemoryItem(
                            id=item.get("id", ""),
                            content=item.get("text", ""),
                            type="short_term",
                            metadata=item.get("metadata", {}),
                            relevance=item.get("score", 0.0),
                        )
                    )
            except Exception as exc:
                logger.warning("STM retrieval failed: %s", exc)

            # 长期记忆检索
            try:
                ltm_results = self.long_term.retrieve(
                    self._INDEX_NAME, query, top_k=half,
                )
                for item in ltm_results:
                    results.append(
                        MemoryItem(
                            id=item.get("id", ""),
                            content=item.get("text", ""),
                            type="long_term",
                            metadata=item.get("metadata", {}),
                            relevance=item.get("score", 0.0),
                        )
                    )
            except Exception as exc:
                logger.warning("LTM retrieval failed: %s", exc)
        else:
            # Fallback: 简单关键词匹配
            query_words = query.lower().split()
            for item in self._fallback_memory[-max_items:]:
                if any(w in item.content.lower() for w in query_words):
                    results.append(
                        MemoryItem(
                            id=item.id,
                            content=item.content,
                            type=item.type,
                            metadata=item.metadata,
                            relevance=0.5,
                        )
                    )

            # 没找到匹配项时，返回最近的短期记忆作为上下文
            if not results:
                recent = [m for m in self._fallback_memory if m.type == "short_term"]
                for item in recent[-2:]:
                    results.append(
                        MemoryItem(
                            id=item.id,
                            content=item.content,
                            type=item.type,
                            metadata=item.metadata,
                            relevance=0.1,
                        )
                    )

        results.sort(key=lambda x: x.relevance, reverse=True)
        return results[:max_items]

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    async def clear_short_term(self) -> None:
        """清除短期记忆"""
        if self._available:
            stm_name = f"studio_stm_{self.session_id}"
            self.short_term = __import__(
                "neuromem.memory_collection.unified_collection",
                fromlist=["UnifiedCollection"],
            ).UnifiedCollection(stm_name, storage_backend="memory")
            self.short_term.add_index(self._INDEX_NAME, "bm25")
        else:
            self._fallback_memory = [
                m for m in self._fallback_memory if m.type != "short_term"
            ]

    async def get_summary(self) -> dict[str, Any]:
        """获取记忆摘要"""
        if self._available:
            return {
                "short_term_count": self.short_term.size(),
                "long_term_count": self.long_term.size(),
                "available": True,
            }
        return {
            "short_term_count": sum(
                1 for m in self._fallback_memory if m.type == "short_term"
            ),
            "long_term_count": sum(
                1 for m in self._fallback_memory if m.type == "long_term"
            ),
            "available": False,
        }


# 会话记忆缓存
_memory_instances: dict[str, MemoryIntegrationService] = {}


def get_memory_service(session_id: str) -> MemoryIntegrationService:
    """获取会话的记忆服务"""
    if session_id not in _memory_instances:
        _memory_instances[session_id] = MemoryIntegrationService(session_id)
    return _memory_instances[session_id]
