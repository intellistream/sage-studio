"""
Node Registry - Maps Studio UI node types to SAGE Operators
"""

import logging
import re
from importlib import import_module

from sage.common.core.functions import MapFunction as MapOperator

from .node_manifest import NODE_PLUGIN_MANIFEST

logger = logging.getLogger(__name__)


def convert_node_type_to_snake_case(node_type: str) -> str:
    """
    将节点类型从 PascalCase 或 camelCase 转换为 snake_case

    Examples:
        TerminalSink -> terminal_sink
        FileSource -> file_source
        HFGenerator -> hf_generator
        OpenAIGenerator -> openai_generator
        QAPromptor -> qa_promptor
    """
    # 特殊处理已知的缩写词,避免拆分
    # OpenAI, QA, HF 等应该保持连在一起
    special_cases = {
        "OpenAI": "openai",
        "QA": "qa",
        "HF": "hf",
        "BGE": "bge",
        "LLM": "llm",
    }

    result = node_type
    for pascal, snake in special_cases.items():
        result = result.replace(pascal, snake.upper() + "_TEMP_")

    # 处理普通驼峰转换
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", result)
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)

    # 转小写并清理临时标记
    s3 = s2.lower().replace("_temp_", "")

    # 清理多余的下划线
    s4 = re.sub("_+", "_", s3).strip("_")

    return s4


class NodeRegistry:
    """Node Registry - Mapping from Studio UI node types to SAGE Operator classes"""

    def __init__(self):
        """Initialize Registry and register all available node types"""
        self._registry: dict[str, type[MapOperator]] = {}
        self._diagnostics: dict[str, dict[str, str]] = {}
        self._register_default_operators()

    def _register_from_manifest(self):
        for item in NODE_PLUGIN_MANIFEST:
            node_type = item["node_type"]
            module_name = item["module"]
            symbol_name = item["symbol"]
            try:
                module = import_module(module_name)
                operator_class = getattr(module, symbol_name)
                self._registry[node_type] = operator_class
                self._diagnostics[node_type] = {
                    "status": "available",
                    "module": module_name,
                    "symbol": symbol_name,
                }
            except Exception as exc:
                self._diagnostics[node_type] = {
                    "status": "missing",
                    "module": module_name,
                    "symbol": symbol_name,
                    "error": str(exc),
                }

    def _register_default_operators(self):
        """Register default Operator mappings"""

        # Generic map operator
        self._registry["map"] = MapOperator
        self._register_from_manifest()

        # ------------------------------------------------------------------
        # RAG Generators
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import (
                HFGenerator,
                OpenAIGenerator,
                SageLLMRAGGenerator,
            )

            self._registry["openai_generator"] = OpenAIGenerator
            self._registry["hf_generator"] = HFGenerator
            self._registry["sagellm_rag_generator"] = SageLLMRAGGenerator
            self._registry["generator"] = OpenAIGenerator  # Default generator
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # RAG Retrievers
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import (
                ChromaRetriever,
                MilvusDenseRetriever,
                MilvusSparseRetriever,
                Wiki18FAISSRetriever,
            )

            self._registry["chroma_retriever"] = ChromaRetriever
            self._registry["milvus_dense_retriever"] = MilvusDenseRetriever
            self._registry["milvus_sparse_retriever"] = MilvusSparseRetriever
            self._registry["wiki18_faiss_retriever"] = Wiki18FAISSRetriever
            self._registry["retriever"] = ChromaRetriever  # Default retriever
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # RAG Rerankers
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import BGEReranker, LLMbased_Reranker

            self._registry["bge_reranker"] = BGEReranker
            self._registry["llm_reranker"] = LLMbased_Reranker
            self._registry["reranker"] = BGEReranker  # Default reranker
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # RAG Promptors
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import (
                QAPromptor,
                QueryProfilerPromptor,
                SummarizationPromptor,
            )

            self._registry["qa_promptor"] = QAPromptor
            self._registry["summarization_promptor"] = SummarizationPromptor
            self._registry["query_profiler_promptor"] = QueryProfilerPromptor
            self._registry["promptor"] = QAPromptor  # Default promptor
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # Document Processing
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import RefinerOperator
            from sage.middleware.operators.rag.chunk import CharacterSplitter

            self._registry["character_splitter"] = CharacterSplitter
            self._registry["refiner"] = RefinerOperator
            self._registry["chunker"] = CharacterSplitter  # Default chunker
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # Memory Writer
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import MemoryWriter

            self._registry["memory_writer"] = MemoryWriter
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # Web Search
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import BochaWebSearch

            self._registry["bocha_web_search"] = BochaWebSearch
            self._registry["web_search"] = BochaWebSearch  # Default web search
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # Evaluation Operators
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.rag import (
                AccuracyEvaluate,
                F1Evaluate,
                RecallEvaluate,
            )

            self._registry["f1_evaluate"] = F1Evaluate
            self._registry["recall_evaluate"] = RecallEvaluate
            self._registry["accuracy_evaluate"] = AccuracyEvaluate
            self._registry["evaluator"] = F1Evaluate  # Default evaluator
        except ImportError:
            pass

        # Source Operators (用于 Pipeline 构建，但不作为 MapOperator 验证)
        try:
            from sage.libs.foundation.io.source import (
                CSVFileSource,
                FileSource,
                JSONFileSource,
                TextFileSource,
            )

            # 注册为特殊类型，PipelineBuilder 会特殊处理
            self._registry["file_source"] = FileSource  # type: ignore
            self._registry["csv_file_source"] = CSVFileSource  # type: ignore
            self._registry["json_file_source"] = JSONFileSource  # type: ignore
            self._registry["text_file_source"] = TextFileSource  # type: ignore
        except ImportError as e:
            logger.warning("Could not import Source operators", extra={"error": str(e)})

        # Sink Operators (用于 Pipeline 构建，但不作为 MapOperator 验证)
        try:
            from sage.libs.foundation.io.sink import (
                FileSink,
                MemWriteSink,
                PrintSink,
                TerminalSink,
            )

            # 注册为特殊类型，PipelineBuilder 会特殊处理
            self._registry["print_sink"] = PrintSink  # type: ignore
            self._registry["terminal_sink"] = TerminalSink  # type: ignore
            self._registry["file_sink"] = FileSink  # type: ignore
            self._registry["mem_write_sink"] = MemWriteSink  # type: ignore
        except ImportError as e:
            logger.warning("Could not import Sink operators", extra={"error": str(e)})

        # ------------------------------------------------------------------
        # Context I/O (ContextFileSource / ContextFileSink)
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.filters import ContextFileSink, ContextFileSource

            self._registry["context_file_source"] = ContextFileSource  # type: ignore
            self._registry["context_file_sink"] = ContextFileSink  # type: ignore
        except ImportError:
            pass

        # ------------------------------------------------------------------
        # Pipeline Filters
        # ------------------------------------------------------------------
        try:
            from sage.middleware.operators.filters import EvaluateFilter, ToolFilter

            self._registry["evaluate_filter"] = EvaluateFilter  # type: ignore
            self._registry["tool_filter"] = ToolFilter  # type: ignore
        except ImportError:
            pass

    def register(self, node_type: str, operator_class: type[MapOperator]):
        """Register a new node type"""
        self._registry[node_type] = operator_class

    def get_operator(self, node_type: str) -> type[MapOperator] | None:
        """Get the Operator class for a node type"""
        return self._registry.get(node_type)

    def list_types(self) -> list[str]:
        """List all registered node types"""
        return sorted(self._registry.keys())

    def diagnose_dependencies(self) -> list[dict[str, str]]:
        """Return plugin availability diagnostics for API/UI display."""
        return [
            {"node_type": node_type, **diagnostic}
            for node_type, diagnostic in sorted(self._diagnostics.items())
        ]


# Singleton instance
_default_registry = None


def get_node_registry() -> NodeRegistry:
    """Get the default NodeRegistry instance (singleton pattern)"""
    global _default_registry
    if _default_registry is None:
        _default_registry = NodeRegistry()
    return _default_registry
