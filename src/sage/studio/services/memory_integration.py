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
        from neuromem.memory_collection.unified_collection import UnifiedCollection

        stm_name = f"studio_stm_{self.session_id}"
        ltm_name = f"studio_ltm_{self.session_id}"

        self.short_term = UnifiedCollection(stm_name, storage_backend="memory")
        self.long_term = UnifiedCollection(ltm_name, storage_backend="memory")

        # 添加 BM25 索引用于文本检索
        self.short_term.add_index(self._INDEX_NAME, "bm25")
        self.long_term.add_index(self._INDEX_NAME, "bm25")

        logger.info("NeuroMem initialized for session %s", self.session_id)

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

        self.short_term.insert(
            text=content,
            metadata={"type": "interaction", **metadata},
            index_names=[self._INDEX_NAME],
        )

    async def add_knowledge(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加知识到长期记忆"""
        metadata = metadata or {}

        self.long_term.insert(
            text=content,
            metadata={"type": "knowledge", **metadata},
            index_names=[self._INDEX_NAME],
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
        half = max(max_items // 2, 1)

        # 短期记忆检索
        try:
            stm_results = self.short_term.retrieve(
                self._INDEX_NAME,
                query,
                top_k=half,
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
                self._INDEX_NAME,
                query,
                top_k=half,
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

        results.sort(key=lambda x: x.relevance, reverse=True)
        return results[:max_items]

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    async def clear_short_term(self) -> None:
        """清除短期记忆"""
        from neuromem.memory_collection.unified_collection import UnifiedCollection

        stm_name = f"studio_stm_{self.session_id}"
        self.short_term = UnifiedCollection(stm_name, storage_backend="memory")
        self.short_term.add_index(self._INDEX_NAME, "bm25")

    async def get_summary(self) -> dict[str, Any]:
        """获取记忆摘要"""
        return {
            "short_term_count": self.short_term.size(),
            "long_term_count": self.long_term.size(),
        }


# 会话记忆缓存
_memory_instances: dict[str, MemoryIntegrationService] = {}


def get_memory_service(session_id: str) -> MemoryIntegrationService:
    """获取会话的记忆服务"""
    if session_id not in _memory_instances:
        _memory_instances[session_id] = MemoryIntegrationService(session_id)
    return _memory_instances[session_id]
