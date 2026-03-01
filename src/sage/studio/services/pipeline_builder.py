"""
Pipeline Builder - 将 Studio 可视化模型转换为 SAGE Pipeline

职责：
1. 解析 VisualPipeline 的节点和连接
2. 拓扑排序节点以确定执行顺序
3. 将每个节点映射到对应的 SAGE Operator
4. 使用 SAGE DataStream API 构建 Pipeline
5. 返回可执行的 Environment

不负责：
- 执行 Pipeline（由 SAGE Engine 完成）
- UI 交互逻辑
- 状态管理（由 SAGE Engine 完成）
"""

import logging
from collections import defaultdict, deque

from sage.common.config.user_paths import get_user_paths

# 从 SAGE 公共 API 导入（参考 PACKAGE_ARCHITECTURE.md）
from sage.kernel.api import LocalEnvironment
from sage.kernel.api.base_environment import BaseEnvironment
from sage.libs.foundation.io.sink import (
    FileSink,
    MemWriteSink,
    RetriveSink,
    TerminalSink,
)
from sage.libs.foundation.io.source import (
    APISource,
    CSVFileSource,
    DatabaseSource,
    FileSource,
    JSONFileSource,
    KafkaSource,
    SocketSource,
    TextFileSource,
)

from ..models import VisualNode, VisualPipeline
from .node_registry import get_node_registry

logger = logging.getLogger(__name__)


class PipelineBuilder:
    """
    将 Studio 的可视化 Pipeline 转换为 SAGE 可执行 Pipeline

    Usage:
        builder = PipelineBuilder()
        env = builder.build(visual_pipeline)
        job = env.execute()
    """

    def __init__(self):
        # 使用全局节点注册表
        self.registry = get_node_registry()
        self._user_input = None  # Playground/Chat 模式的用户输入
        self._env_config = {}  # 缓存环境配置

    def build(self, pipeline: VisualPipeline, user_input: str = None) -> BaseEnvironment:
        """
        从 VisualPipeline 构建 SAGE Pipeline

        Args:
            pipeline: Studio 的可视化 Pipeline 模型
            user_input: Playground/Chat 模式的用户输入 (可选)

        Returns:
            配置好的 SAGE 执行环境

        Raises:
            ValueError: 如果 Pipeline 结构无效
        """
        # 🆕 加载环境变量
        self._load_environment_variables()

        # 🆕 保存用户输入
        self._user_input = user_input

        # 1. 验证 Pipeline
        self._validate_pipeline(pipeline)

        # 2. 拓扑排序节点
        sorted_nodes = self._topological_sort(pipeline)

        # 3. 创建执行环境
        env = LocalEnvironment()

        # 4. 构建 DataStream Pipeline
        stream = None
        node_outputs = {}  # 记录每个节点的输出 stream

        for node in sorted_nodes:
            operator_class = self._get_operator_class(node.type)

            if stream is None:
                # 第一个节点 - 创建 source
                source_class, source_args, source_kwargs = self._create_source(node, pipeline)
                stream = env.from_source(
                    source_class, *source_args, name=node.label, **source_kwargs
                )
            else:
                # 🆕 增强配置
                enhanced_config = self._enhance_operator_config(operator_class, node.config)

                # 后续节点 - 添加 transformation
                stream = stream.map(operator_class, config=enhanced_config, name=node.label)

            node_outputs[node.id] = stream

        # 5. 添加 sink
        if stream:
            stream.sink(self._create_sink(pipeline))

        return env

    def build_with_diagnostics(
        self, pipeline: VisualPipeline, user_input: str = None
    ) -> tuple[BaseEnvironment | None, dict]:
        """Build pipeline and return structured diagnostics on failure."""
        try:
            env = self.build(pipeline, user_input=user_input)
            return env, {"ok": True, "diagnostics": []}
        except Exception as exc:
            diagnostics = {
                "ok": False,
                "error": str(exc),
                "registry": self.registry.diagnose_dependencies(),
            }
            logger.error("Pipeline build failed", extra=diagnostics)
            return None, diagnostics

    def _validate_pipeline(self, pipeline: VisualPipeline):
        """验证 Pipeline 结构的有效性"""
        if not pipeline.nodes:
            raise ValueError("Pipeline must contain at least one node")

        # 检查所有节点类型是否已注册
        for node in pipeline.nodes:
            # Source 和 Sink 节点在 Registry 中有注册，但类型不同于 MapOperator
            # 它们会在 build() 中被特殊处理，所以这里只检查是否存在
            if self.registry.get_operator(node.type) is None:
                # 提供更友好的错误信息
                available_types = self.registry.list_types()
                error_msg = (
                    f"Unknown node type: '{node.type}'. \n"
                    f"Available types ({len(available_types)}): {available_types[:10]}... \n"
                    f"Hint: Node type should be in snake_case (e.g., 'terminal_sink', not 'TerminalSink')"
                )
                raise ValueError(error_msg)

        # 检查连接是否有效
        node_ids = {node.id for node in pipeline.nodes}
        for conn in pipeline.connections:
            if conn.source_node_id not in node_ids:
                raise ValueError(f"Connection source not found: {conn.source_node_id}")
            if conn.target_node_id not in node_ids:
                raise ValueError(f"Connection target not found: {conn.target_node_id}")

    def _topological_sort(self, pipeline: VisualPipeline) -> list[VisualNode]:
        """
        对节点进行拓扑排序

        Returns:
            排序后的节点列表

        Raises:
            ValueError: 如果存在循环依赖
        """
        # 构建依赖图
        in_degree = defaultdict(int)
        adjacency = defaultdict(list)
        node_map = {node.id: node for node in pipeline.nodes}

        # 初始化入度
        for node in pipeline.nodes:
            in_degree[node.id] = 0

        # 构建图
        for conn in pipeline.connections:
            adjacency[conn.source_node_id].append(conn.target_node_id)
            in_degree[conn.target_node_id] += 1

        # Kahn 算法
        queue = deque([node_id for node_id in in_degree if in_degree[node_id] == 0])
        sorted_nodes = []

        while queue:
            node_id = queue.popleft()
            sorted_nodes.append(node_map[node_id])

            for neighbor in adjacency[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检查是否存在循环
        if len(sorted_nodes) != len(pipeline.nodes):
            remaining = [n.label for n in pipeline.nodes if n not in sorted_nodes]
            raise ValueError(
                f"Circular dependency detected in pipeline. Nodes in cycle: {remaining}"
            )

        return sorted_nodes

    def _load_environment_variables(self) -> None:
        """
        从用户配置目录加载环境变量

        支持的变量:
        - OPENAI_API_KEY: OpenAI API
        - 其他自定义环境变量
        """
        import json
        import os

        env_file = get_user_paths().config_dir / "studio.env.json"
        if env_file.exists():
            try:
                with open(env_file) as f:
                    env_vars = json.load(f)
                    self._env_config = env_vars  # 缓存配置
                    for key, value in env_vars.items():
                        os.environ[key] = value
                logger.info(
                    "Loaded Studio environment config", extra={"keys": list(env_vars.keys())}
                )
            except Exception as e:
                logger.error("Failed to load Studio environment config", extra={"error": str(e)})
        else:
            logger.info("Studio environment config file not found", extra={"path": str(env_file)})

    def _load_env_from_config(self) -> dict:
        """从缓存的配置中读取环境变量"""
        return self._env_config

    def _probe_url(self, url: str, timeout: float = 2.0) -> bool:
        """探测端点是否可用

        Args:
            url: 要探测的端点 URL
            timeout: 超时时间（秒）

        Returns:
            bool: 端点是否可用
        """
        try:
            import requests

            response = requests.get(f"{url.rstrip('/')}/models", timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    def _enhance_operator_config(self, operator_class, config: dict) -> dict:
        """
        增强 operator 配置

        功能:
        1. OpenAIGenerator: 智能 Qwen/GPT API key 选择
        2. ChromaRetriever: 默认 ChromaDB 路径和参数
        3. 其他: 保持原配置
        """
        import os
        from pathlib import Path

        enhanced = config.copy()
        operator_name = operator_class.__name__

        # OpenAIGenerator: 智能 API key 配置
        if operator_name == "OpenAIGenerator":
            model = config.get("model", config.get("model_name", ""))

            # 确保 model_name 字段存在
            if "model_name" not in enhanced and model:
                enhanced["model_name"] = model

            # 确保总是有 api_key 字段（即使为 None）
            if "api_key" not in enhanced:
                api_key = (
                    os.environ.get("SAGE_PIPELINE_BUILDER_API_KEY")
                    or os.environ.get("SAGE_CHAT_API_KEY")
                    or os.environ.get("OPENAI_API_KEY")
                    or self._load_env_from_config().get("SAGE_PIPELINE_BUILDER_API_KEY")
                    or self._load_env_from_config().get("SAGE_CHAT_API_KEY")
                )
                enhanced["api_key"] = api_key

            # 确保 base_url 字段存在（如果还没有），本地优先
            if "base_url" not in enhanced:
                from sage.studio.config.ports import StudioPorts

                # 优先探测本地 LLM 端点（8001 → 8901）
                detected = None
                for port in [
                    StudioPorts.get_recommended_llm_port(),
                    StudioPorts.LLM_DEFAULT,
                    StudioPorts.SAGELLM_SERVE_PORT,
                ]:
                    candidate = f"http://127.0.0.1:{port}/v1"
                    if self._probe_url(candidate):
                        detected = candidate
                        break

                if detected:
                    enhanced["base_url"] = detected
                    logger.info("Detected local LLM endpoint", extra={"base_url": detected})
                else:
                    # 回落到显式配置的 OPENAI_BASE_URL（若存在），否则留空由上游处理
                    env_base = os.environ.get("OPENAI_BASE_URL")
                    if env_base:
                        enhanced["base_url"] = env_base
                        logger.info("Using explicit OPENAI_BASE_URL", extra={"base_url": env_base})

        # ChromaRetriever: 默认 ChromaDB 配置
        elif operator_name == "ChromaRetriever":
            if "persist_directory" not in enhanced:
                chroma_path = Path.home() / ".sage" / "vector_db"
                enhanced["persist_directory"] = str(chroma_path)

            if "collection_name" not in enhanced:
                enhanced["collection_name"] = "sage_docs"

            if "top_k" not in enhanced:
                enhanced["top_k"] = 5

            logger.info(
                "Configured ChromaRetriever defaults",
                extra={
                    "collection_name": enhanced["collection_name"],
                    "top_k": enhanced["top_k"],
                },
            )

        return enhanced

    def _get_operator_class(self, node_type: str):
        """获取节点类型对应的 Operator 类"""
        operator_class = self.registry.get_operator(node_type)
        if not operator_class:
            raise ValueError(
                f"Unknown node type: {node_type}. Available types: {self.registry.list_types()}"
            )
        return operator_class

    def _create_source(self, node: VisualNode, pipeline: VisualPipeline):
        """
        根据节点类型和配置创建合适的数据源

        Returns:
            tuple: (source_class, args, kwargs)

        支持的源类型：
        - file: FileSource (文件路径)
        - json_file: JSONFileSource (JSON 文件)
        - csv_file: CSVFileSource (CSV 文件)
        - text_file: TextFileSource (文本文件)
        - socket: SocketSource (网络 socket)
        - kafka: KafkaSource (Kafka topic)
        - database: DatabaseSource (数据库查询)
        - api: APISource (HTTP API)
        - memory/data: 内存数据源（用于测试）
        """
        from sage.common.core import SourceFunction

        source_type = node.config.get("source_type", "memory")

        # 文件源
        if source_type == "file":
            file_path = node.config.get("file_path", node.config.get("path"))
            return FileSource, (file_path,), {}

        elif source_type == "json_file":
            file_path = node.config.get("file_path", node.config.get("path"))
            return JSONFileSource, (file_path,), {}

        elif source_type == "csv_file":
            file_path = node.config.get("file_path", node.config.get("path"))
            delimiter = node.config.get("delimiter", ",")
            return CSVFileSource, (file_path, delimiter), {}

        elif source_type == "text_file":
            file_path = node.config.get("file_path", node.config.get("path"))
            return TextFileSource, (file_path,), {}

        # 网络源
        elif source_type == "socket":
            host = node.config.get("host", "localhost")
            port = node.config.get("port", 9999)
            return SocketSource, (host, port), {}

        elif source_type == "kafka":
            topic = node.config.get("topic")
            bootstrap_servers = node.config.get("bootstrap_servers", "localhost:9092")
            return KafkaSource, (topic, bootstrap_servers), {}

        # 数据库源
        elif source_type == "database":
            query = node.config.get("query")
            connection_string = node.config.get("connection_string")
            return DatabaseSource, (query, connection_string), {}

        # API 源
        elif source_type == "api":
            url = node.config.get("url")
            method = node.config.get("method", "GET")
            return APISource, (url, method), {}

        # 内存数据源（默认，用于测试）
        else:

            class SimpleListSource(SourceFunction):
                """Simple in-memory list source for testing and development"""

                def __init__(self, data):
                    super().__init__()
                    self.data = data if isinstance(data, list) else [data]

                def execute(self, data=None):
                    """Execute the source function"""
                    return self.data

            # 🆕 优先使用外部输入
            if hasattr(self, "_user_input") and self._user_input:
                initial_data = [{"input": self._user_input}]
                print(f"  ✓ 使用输入: {self._user_input[:50]}...")
            else:
                initial_data = node.config.get("data", [{"input": "test data"}])
            return SimpleListSource, (initial_data,), {}

    def _create_sink(self, pipeline: VisualPipeline):
        """
        根据 Pipeline 配置创建合适的数据接收器

        Returns:
            Type: Sink class (not instance)

        支持的接收器类型：
        - terminal: TerminalSink (终端输出，带颜色)
        - print: PrintSink (简单打印)
        - file: FileSink (文件输出)
        - memory: MemWriteSink (内存写入，用于测试)
        - retrieve: RetriveSink (收集结果)
        """

        # 从 pipeline 的 execution_mode 或其他配置中获取 sink 类型
        # 🆕 Playground/Chat 模式默认使用 retrieve 收集结果
        sink_type = getattr(pipeline, "sink_type", "retrieve")

        if sink_type == "terminal":
            return TerminalSink
        elif sink_type == "file":
            return FileSink
        elif sink_type == "memory":
            return MemWriteSink
        elif sink_type == "retrieve":
            return RetriveSink
        else:
            # 默认使用 RetriveSink (Playground/Chat 模式)
            return RetriveSink


# 全局 Builder 实例
_default_builder = None


def get_pipeline_builder() -> PipelineBuilder:
    """获取全局 PipelineBuilder 实例"""
    global _default_builder
    if _default_builder is None:
        _default_builder = PipelineBuilder()
    return _default_builder
