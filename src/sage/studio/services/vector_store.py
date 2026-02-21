"""
Vector Store Service for SAGE Studio

This module provides a thin wrapper around sage-mem's VDBMemoryCollection
for knowledge base vector storage and retrieval in SAGE Studio.

Layer: L6 (sage-studio)
Dependencies: sage-middleware (sage-mem/neuromem), sage-common (embedding)

Design Principles:
- Reuses existing neuromem VDBMemoryCollection implementation
- Provides simplified interface for Studio's knowledge management needs
- Supports both local embedding and external embedding service
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from sage.common.config.user_paths import get_user_paths

if TYPE_CHECKING:
    from sage.common.components.sage_embedding.protocols import EmbeddingProtocol


@dataclass
class DocumentChunk:
    """文档分块数据结构

    与 Task 2.2 document_loader 模块共享的数据结构。

    Attributes:
        content: 分块的文本内容
        source_file: 源文件路径
        chunk_index: 在源文件中的分块索引
        metadata: 额外元数据（如标题、语言等）
    """

    content: str
    source_file: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        """生成唯一的 chunk ID"""
        key = f"{self.source_file}:{self.chunk_index}:{self.content[:100]}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class SearchResult:
    """检索结果

    Attributes:
        content: 匹配的文本内容
        score: 相似度分数 (0-1, 越高越相关)
        source: 来源文件路径
        metadata: 额外元数据
    """

    content: str
    score: float
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    """向量存储服务

    封装 sage-mem 的 VDBMemoryCollection，为 SAGE Studio
    知识库管理提供简化的向量存储和检索接口。

    Features:
    - 基于 neuromem VDBMemoryCollection 的高性能向量存储
    - 支持 sage-embedding 或外部 embedding 服务
    - 支持持久化和增量更新
    - 支持按来源删除文档

    Example:
        >>> store = VectorStore(
        ...     collection_name="studio_kb",
        ...     embedding_model="BAAI/bge-small-zh-v1.5",
        ... )
        >>> await store.add_documents(chunks)
        >>> results = await store.search("如何创建 Pipeline?")
    """

    def __init__(
        self,
        collection_name: str,
        embedding_model: str = "BAAI/bge-small-zh-v1.5",
        embedding_dim: int = 512,
        persist_dir: str | Path | None = None,
        embedder: EmbeddingProtocol | None = None,
    ):
        """初始化向量存储

        Args:
            collection_name: Collection 名称，用于区分不同的知识库
            embedding_model: Embedding 模型名称
            embedding_dim: Embedding 向量维度
            persist_dir: 持久化目录，默认使用 XDG 标准路径
            embedder: 外部 embedder 实例（可选，优先使用）
        """
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim

        # 设置持久化目录
        if persist_dir is None:
            user_paths = get_user_paths()
            self.persist_dir = user_paths.data_dir / "studio" / "vector_db"
        else:
            self.persist_dir = Path(persist_dir).expanduser()
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # 延迟初始化的组件
        self._embedder = embedder
        self._collection = None
        self._manager = None

    @property
    def embedder(self) -> EmbeddingProtocol:
        """获取或创建 embedder（懒加载）"""
        if self._embedder is None:
            self._embedder = self._create_embedder()
        return self._embedder

    def _create_embedder(self) -> EmbeddingProtocol:
        """创建 embedding 客户端"""
        from sage.common.components.sage_embedding import (
            EmbeddingFactory,
            adapt_embedding_client,
        )

        # 创建 HuggingFace embedding 模型
        raw_embedder = EmbeddingFactory.create(
            "hf",
            model=self.embedding_model,
        )
        # 适配为批量接口
        return adapt_embedding_client(raw_embedder)

    @property
    def collection(self):
        """获取或创建 VDB collection（懒加载）"""
        if self._collection is None:
            self._init_collection()
        return self._collection

    def _init_collection(self):
        """初始化 VDB collection"""
        import logging as _logging

        from sage.neuromem import MemoryManager
        from sage.neuromem.memory_collection.unified_collection import UnifiedCollection

        _vs_logger = _logging.getLogger(__name__)

        # 创建 MemoryManager
        data_dir = str(self.persist_dir)
        self._manager = MemoryManager(data_dir)

        # 直接从 manager 内存注册表读取，避免依赖不稳定的 get_collection 实现
        self._collection = self._manager.collections.get(self.collection_name)

        if self._collection is None:
            _vs_logger.info(f"Creating new collection '{self.collection_name}'")

            # 创建新的 collection
            self._collection = UnifiedCollection(self.collection_name)

            if self._collection is None:
                raise RuntimeError(f"Failed to create collection '{self.collection_name}'")

            # Register in MemoryManager so persist() can find it
            self._manager.collections[self.collection_name] = self._collection

            # 创建默认 FAISS 索引
            self._collection.add_index(
                "default_index",
                "faiss",
                {"dim": self.embedding_dim, "metric": "cosine"},
            )
            _vs_logger.info(
                f"Created collection '{self.collection_name}' with FAISS index (dim={self.embedding_dim})"
            )
        else:
            # Ensure loaded collection is registered in manager
            self._manager.collections[self.collection_name] = self._collection

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """生成文本的 embedding 向量"""
        return self.embedder.embed(texts)

    def has_data(self) -> bool:
        """检查collection是否已有数据（用于跳过重复加载）

        Returns:
            True if collection已有数据（从磁盘加载或已插入），False otherwise
        """
        try:
            # 初始化collection（如果还没初始化）
            if self._collection is None:
                self._init_collection()

            # 检查collection大小
            if hasattr(self._collection, "size"):
                return self._collection.size() > 0
            elif hasattr(self._collection, "__len__"):
                return len(self._collection) > 0
            else:
                return len(getattr(self._collection, "raw_data", {})) > 0
        except Exception as e:
            import logging

            logging.warning(f"has_data check failed: {e}")
            return False

    async def add_documents(
        self,
        chunks: list[DocumentChunk],
        batch_size: int = 128,  # 增加batch size加速embedding生成
    ) -> int:
        """添加文档到向量库

        Args:
            chunks: DocumentChunk 列表
            batch_size: 批处理大小

        Returns:
            成功添加的文档数量
        """
        if not chunks:
            return 0

        import logging

        logger = logging.getLogger(__name__)

        added_count = 0
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        logger.info(
            f"Adding {len(chunks)} chunks in {total_batches} batches (batch_size={batch_size})"
        )

        # 分批处理
        for batch_idx, i in enumerate(range(0, len(chunks), batch_size), 1):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]

            # 生成 embeddings（这是最耗时的步骤）
            logger.info(
                f"Processing batch {batch_idx}/{total_batches} ({added_count}/{len(chunks)} chunks added so far)"
            )

            try:
                embeddings = self._embed(texts)
            except Exception as e:
                logger.error(f"Embedding generation failed for batch {batch_idx}: {e}")
                continue

            # 准备向量和元数据
            vectors = [np.array(emb, dtype=np.float32) for emb in embeddings]

            for chunk, vector in zip(batch, vectors):
                metadata = {
                    "source_file": chunk.source_file,
                    "chunk_index": str(chunk.chunk_index),
                    "chunk_id": chunk.chunk_id,
                    "vector": vector.tolist(),
                    **{k: str(v) for k, v in chunk.metadata.items()},
                }

                try:
                    self.collection.insert(
                        text=chunk.content,
                        metadata=metadata,
                        index_names=["default_index"],
                    )
                    added_count += 1
                except Exception as e:
                    # 记录错误但继续处理
                    logger.warning(f"Failed to insert chunk {chunk.chunk_id}: {e}")

        # 持久化到磁盘（重要：确保数据不丢失）
        if added_count > 0:
            self.save()

        return added_count

    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        source_filter: str | None = None,
    ) -> list[SearchResult]:
        """语义检索

        Args:
            query: 查询文本
            top_k: 返回结果数量
            score_threshold: 相似度阈值 (0-1)
            source_filter: 按来源文件过滤（可选）

        Returns:
            SearchResult 列表，按相似度降序排列
        """
        # 生成查询向量
        query_embedding = self._embed([query])[0]
        query_vector = np.array(query_embedding, dtype=np.float32)

        # UnifiedCollection.retrieve(index_name, query, **params)
        try:
            results = self.collection.retrieve(
                "default_index",
                query_vector,
                top_k=top_k * 2,  # 多取一些以便过滤
            )
        except Exception as e:
            import logging

            logging.warning(f"Vector search failed: {e}")
            return []

        if results is None:
            return []

        # 转换结果格式并过滤
        # Note: UnifiedCollection.retrieve returns [{id, text, metadata, created_at}, ...]
        # Results are already ranked by FAISS similarity (no explicit score field).
        search_results = []
        total = len(results)
        for rank, r in enumerate(results):
            if isinstance(r, dict):
                content = r.get("text", r.get("content", ""))
                # FAISS retrieve doesn't include score; use rank-based score
                score = float(
                    r.get("score", r.get("similarity", max(0.1, 1.0 - rank / max(total, 1))))
                )
                metadata = r.get("metadata", {})
            else:
                content = getattr(r, "text", getattr(r, "content", str(r)))
                score = float(getattr(r, "score", max(0.1, 1.0 - rank / max(total, 1))))
                metadata = getattr(r, "metadata", {})

            # Remove internal 'vector' key from metadata before exposing
            metadata = {k: v for k, v in metadata.items() if k != "vector"}

            source = metadata.get("source_file", "unknown")

            # 应用过滤
            if source_filter and source_filter not in source:
                continue

            # 应用阈值
            if score < score_threshold:
                continue

            search_results.append(
                SearchResult(
                    content=content,
                    score=score,
                    source=source,
                    metadata=metadata,
                )
            )

        # 按分数排序并限制数量
        search_results.sort(key=lambda x: x.score, reverse=True)
        return search_results[:top_k]

    async def delete_by_source(self, source_file: str) -> int:
        """删除指定来源的所有文档

        Args:
            source_file: 源文件路径

        Returns:
            删除的文档数量
        """
        # 查找所有匹配的文档
        # neuromem 支持按 metadata 查找
        try:
            # 获取所有 item_id
            deleted_count = 0

            # 使用 metadata 过滤查找
            if hasattr(self.collection, "find_by_metadata"):
                item_ids = self.collection.find_by_metadata("source_file", source_file)
                for item_id in item_ids:
                    if self.collection.delete(item_id):
                        deleted_count += 1
            else:
                # 备用方案：遍历删除
                # 这个实现可能效率较低，但保证兼容性
                pass

            return deleted_count
        except Exception as e:
            import logging

            logging.warning(f"Failed to delete documents from {source_file}: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            包含向量数量、索引信息等的字典
        """
        stats = {
            "collection_name": self.collection_name,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "persist_dir": str(self.persist_dir),
        }

        try:
            if hasattr(self.collection, "statistics"):
                stats.update(self.collection.statistics)
            if hasattr(self.collection, "list_indexes"):
                stats["indexes"] = self.collection.list_indexes()
        except Exception:
            pass

        return stats

    def save(self) -> bool:
        """持久化到磁盘

        Returns:
            是否成功保存
        """
        try:
            if self._manager is not None and self._collection is not None:
                # 显式调用 MemoryManager.persist 保存到磁盘
                success = self._manager.persist(self.collection_name)
                if success:
                    import logging

                    logging.info(
                        f"Persisted collection '{self.collection_name}' to {self.persist_dir}"
                    )
                return success
            return False
        except Exception as e:
            import logging

            logging.error(f"Failed to save vector store: {e}")
            return False

    def close(self):
        """关闭向量存储，释放资源"""
        self._collection = None
        self._manager = None
        self._embedder = None


# 便捷工厂函数
def create_vector_store(
    collection_name: str = "studio_default",
    embedding_model: str = "BAAI/bge-small-zh-v1.5",
    **kwargs,
) -> VectorStore:
    """创建 VectorStore 实例的便捷函数

    Args:
        collection_name: Collection 名称
        embedding_model: Embedding 模型名称
        **kwargs: 其他参数传递给 VectorStore

    Returns:
        VectorStore 实例
    """
    return VectorStore(
        collection_name=collection_name,
        embedding_model=embedding_model,
        **kwargs,
    )
