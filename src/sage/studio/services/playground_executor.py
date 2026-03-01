"""
Playground 执行器 - 负责在 Studio UI 中运行 Pipeline
"""

import logging
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from sage.common.core.functions.sink_function import SinkFunction
from sage.common.core.functions.source_function import SourceFunction
from sage.kernel.api import LocalEnvironment

logger = logging.getLogger(__name__)


class PlaygroundSource(SourceFunction):
    """Playground 输入源 - 将用户输入注入到 Pipeline"""

    def __init__(self, question: str, **kwargs):
        super().__init__(**kwargs)
        self.question = question
        self.sent = False

    def execute(self, data=None):
        if self.sent:
            return None
        self.sent = True
        logger.info(f"📥 PlaygroundSource 发送问题: {self.question}")
        return {"query": self.question}


class PlaygroundSink(SinkFunction):
    """Playground 输出收集器 - 收集 Pipeline 的输出"""

    # 类级别的结果存储（用于在不同实例间共享）
    _shared_results = {}

    def __init__(self, execution_id: str = "default", **kwargs):
        super().__init__(**kwargs)
        self.execution_id = execution_id
        # 初始化该执行的结果列表
        if execution_id not in PlaygroundSink._shared_results:
            PlaygroundSink._shared_results[execution_id] = []

    def execute(self, data):
        logger.info(f"📤 PlaygroundSink 接收到数据: {type(data)}")
        PlaygroundSink._shared_results[self.execution_id].append(data)

    @classmethod
    def get_results(cls, execution_id: str) -> list:
        """获取指定执行的结果"""
        return cls._shared_results.get(execution_id, [])

    @classmethod
    def clear_results(cls, execution_id: str):
        """清理指定执行的结果"""
        if execution_id in cls._shared_results:
            del cls._shared_results[execution_id]


class PlaygroundExecutor:
    """Playground 执行器"""

    def __init__(self):
        self.execution_logs = []
        self.log_handler = None
        self.current_flow_id = None
        self.log_file_handler = None

    def _setup_logging(self, flow_id: str):
        """设置日志捕获（同时写入内存和文件）"""
        self.current_flow_id = flow_id

        # 创建日志目录
        log_dir = Path.home() / ".sage" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{flow_id}.log"

        # 内存日志捕获器
        class LogCapture(logging.Handler):
            def __init__(self, executor):
                super().__init__()
                self.executor = executor

            def emit(self, record):
                log_entry = {
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "logger": record.name,
                }
                self.executor.execution_logs.append(log_entry)

                # 同时写入文件（格式: [timestamp] [level] message）
                if self.executor.log_file_handler:
                    log_line = f"[{log_entry['timestamp']}] [{log_entry['level']}] {log_entry['message']}\n"
                    try:
                        self.executor.log_file_handler.write(log_line)
                        self.executor.log_file_handler.flush()
                    except Exception as e:
                        print(f"Failed to write log: {e}")

        # 打开日志文件
        self.log_file_handler = open(log_file, "a", encoding="utf-8")
        self.log_file_handler.write(f"\n{'=' * 60}\n")
        self.log_file_handler.write(
            f"[{datetime.now().isoformat()}] [SYSTEM] New execution started\n"
        )
        self.log_file_handler.write(f"{'=' * 60}\n")
        self.log_file_handler.flush()

        self.log_handler = LogCapture(self)
        logging.getLogger("sage").addHandler(self.log_handler)
        logging.getLogger("sage").setLevel(logging.INFO)

    def _cleanup_logging(self):
        """清理日志捕获"""
        if self.log_handler:
            logging.getLogger("sage").removeHandler(self.log_handler)
            self.log_handler = None

        if self.log_file_handler:
            try:
                self.log_file_handler.write(
                    f"[{datetime.now().isoformat()}] [SYSTEM] Execution ended\n{'=' * 60}\n\n"
                )
                self.log_file_handler.close()
            except Exception as e:
                print(f"Failed to close log file: {e}")
            self.log_file_handler = None

    def _load_environment_variables(self):
        """加载 Studio 设置的环境变量到系统环境"""
        env_file = Path.home() / ".sage" / ".env.json"
        if env_file.exists():
            try:
                import json

                with open(env_file, encoding="utf-8") as f:
                    env_vars = json.load(f)
                    os.environ.update(env_vars)
                    logger.info(f"✅ 已加载 {len(env_vars)} 个环境变量")
                    for key in env_vars.keys():
                        logger.info(f"   - {key}")
            except Exception as e:
                logger.warning(f"⚠️ 加载环境变量失败: {e}")
        else:
            logger.info("ℹ️ 未找到环境变量配置文件，跳过加载")

    def _convert_config_params(self, op_type: str, config: dict) -> dict:
        """转换 Studio UI 配置参数到算子构造函数期望的格式"""
        converted_config = config.copy()

        # OpenAIGenerator 和 HFGenerator 参数转换
        if op_type in ["OpenAIGenerator", "HFGenerator"]:
            model_name = converted_config.get("model_name", "")
            logger.info(f"   🔍 检测到模型: {model_name}")

            # 判断是否是 Qwen 系列模型
            is_qwen = model_name.lower().startswith("qwen")
            logger.info(f"   🎯 是否为 Qwen 模型: {is_qwen}")

            # 自动设置 API Key（如果配置中为空）
            if not converted_config.get("api_key"):
                api_key = (
                    os.getenv("SAGE_CHAT_API_KEY")
                    or os.getenv("SAGE_PIPELINE_BUILDER_API_KEY")
                    or os.getenv("OPENAI_API_KEY")
                )
                if api_key:
                    converted_config["api_key"] = api_key
                    logger.info(f"   ✅ API Key 已设置（长度: {len(api_key)}）")
                else:
                    logger.warning("   ⚠️ 未找到 SAGE_CHAT_API_KEY / OPENAI_API_KEY")
            else:
                logger.info("   📌 使用配置中的 API Key")

            # 自动设置 API 端点（如果配置中为空或使用旧的默认值）
            api_base = converted_config.get("api_base", "")
            logger.info(f"   🌐 原始 api_base: '{api_base}'")

            if not api_base:
                from sage.studio.config.ports import StudioPorts

                detected = None
                for port in [
                    StudioPorts.get_recommended_llm_port(),
                    StudioPorts.LLM_DEFAULT,
                    StudioPorts.BENCHMARK_LLM,
                ]:
                    candidate = f"http://127.0.0.1:{port}/v1"
                    if self._probe_url(candidate, timeout=1.0):
                        detected = candidate
                        break

                if detected:
                    converted_config["api_base"] = detected
                    logger.info(f"   ✅ 使用本地 LLM 端点: {detected}")
                else:
                    # Fallback to explicitly provided OPENAI_BASE_URL if present
                    explicit_base = os.getenv("OPENAI_BASE_URL")
                    if explicit_base:
                        converted_config["api_base"] = explicit_base
                        logger.info(f"   ✅ 使用 OPENAI_BASE_URL: {explicit_base}")
                    else:
                        logger.warning("   ⚠️ 未找到可用的本地 LLM 端点或 OPENAI_BASE_URL")

            # api_base -> base_url
            if "api_base" in converted_config:
                converted_config["base_url"] = converted_config.pop("api_base")
                logger.info(f"   🔄 转换 api_base -> base_url: {converted_config['base_url']}")

            # 确保有 method 字段
            if "method" not in converted_config:
                converted_config["method"] = "openai" if op_type == "OpenAIGenerator" else "hf"

            # 确保有 seed 字段
            if "seed" not in converted_config:
                converted_config["seed"] = 42

            # 将所有配置包装到 config 字典中（算子期望接收的格式）
            return converted_config

        # ChromaRetriever 参数转换
        elif op_type == "ChromaRetriever":
            # 处理 chroma 配置中的 persistence_path
            if "chroma" in converted_config and isinstance(converted_config["chroma"], dict):
                chroma_config = converted_config["chroma"]
                if "persistence_path" in chroma_config:
                    # 展开 ~ 路径
                    path = chroma_config["persistence_path"]
                    if path.startswith("~"):
                        chroma_config["persistence_path"] = str(Path(path).expanduser())
            return converted_config

        return converted_config

    def _validate_operator_configs(self, operator_configs: list[dict]) -> list[str]:
        """验证操作符配置

        Returns:
            错误信息列表，空列表表示验证通过
        """
        errors = []

        if not operator_configs:
            errors.append("操作符配置列表为空")
            return errors

        for idx, op_config in enumerate(operator_configs, start=1):
            if not isinstance(op_config, dict):
                errors.append(f"节点 {idx}: 配置必须是字典类型")
                continue

            if "type" not in op_config:
                errors.append(f"节点 {idx}: 缺少 'type' 字段")

            if "config" not in op_config:
                errors.append(
                    f"节点 {idx} ({op_config.get('type', 'Unknown')}): 缺少 'config' 字段"
                )
                errors.append("  提示: 从 Chat 推荐生成的工作流可能缺少配置，请手动添加或重新生成")

            # 检查特定操作符的必需配置
            op_type = op_config.get("type")
            config = op_config.get("config", {})

            if op_type in ["OpenAIGenerator", "HFGenerator"]:
                if not config.get("model_name"):
                    errors.append(f"节点 {idx} ({op_type}): 缺少 'model_name' 配置")

            if op_type == "ChromaRetriever":
                if not config.get("persist_directory"):
                    errors.append(f"节点 {idx} ({op_type}): 缺少 'persist_directory' 配置")

        return errors

    def execute_simple_query(
        self, user_input: str, operator_configs: list[dict], flow_id: str = "default"
    ) -> dict[str, Any]:
        """
        执行简单的查询 Pipeline

        Args:
            user_input: 用户输入的问题
            operator_configs: 节点配置列表 [{"type": "ChromaRetriever", "config": {...}}, ...]
            flow_id: Flow ID，用于日志文件命名

        Returns:
            执行结果字典

        修复: 添加配置验证
        """
        # 验证 operator_configs
        validation_errors = self._validate_operator_configs(operator_configs)
        if validation_errors:
            error_msg = "\n".join([f"  - {err}" for err in validation_errors])
            return {
                "success": False,
                "output": f"❌ 配置验证失败:\n{error_msg}\n\n请检查节点配置是否完整。",
                "logs": [],
                "execution_time": 0,
                "error": "Invalid configuration",
            }

        # 生成唯一的执行 ID
        execution_id = f"{flow_id}_{int(time.time() * 1000)}"

        try:
            # 先设置日志，这样环境变量加载的日志才能被捕获
            self._setup_logging(flow_id)

            # 加载环境变量到系统环境
            self._load_environment_variables()

            start_time = time.time()

            logger.info(f"🚀 开始执行 Playground: {len(operator_configs)} 个节点")
            logger.info(f"📝 用户输入: {user_input}")
            logger.info(f"🔑 执行 ID: {execution_id}")

            # 创建环境
            env = LocalEnvironment()

            # 创建输入源（注意：from_source 期望的是类，不是实例）
            # PlaygroundSource 是 SourceFunction 子类，需要以类形式传递
            source_stream = env.from_source(PlaygroundSource, question=user_input)

            # 按顺序添加操作符
            current_stream = source_stream
            for idx, op_config in enumerate(operator_configs, start=1):
                op_type = op_config.get("type")
                op_config_data = op_config.get("config", {})

                logger.info(f"📦 添加节点 {idx}: {op_type}")
                logger.info(f"   原始配置: {op_config_data}")

                # 转换配置参数
                converted_config = self._convert_config_params(op_type, op_config_data)

                # 显示完整的转换后配置（包括敏感信息的掩码）
                display_config = converted_config.copy()
                if "api_key" in display_config and display_config["api_key"]:
                    # 只显示前8位和后4位
                    key = display_config["api_key"]
                    if len(key) > 12:
                        display_config["api_key"] = f"{key[:8]}...{key[-4:]}"
                logger.info(f"   转换后配置: {display_config}")

                # 根据类型加载对应的操作符
                operator_class = self._load_operator(op_type)
                if operator_class:
                    # 大多数 RAG operators 需要 config 作为第一个参数
                    # 只有极少数例外使用 **kwargs 方式
                    rag_config_operators = [
                        "OpenAIGenerator",
                        "HFGenerator",
                        "ChromaRetriever",
                        "SimpleRetriever",
                        "BGEReranker",
                        "LLMbased_Reranker",
                        "QAPromptor",
                        "AbstractiveRecompRefiner",
                    ]

                    if op_type in rag_config_operators:
                        current_stream = current_stream.map(operator_class, config=converted_config)
                    else:
                        current_stream = current_stream.map(operator_class, **converted_config)
                else:
                    logger.warning(f"⚠️ 无法加载操作符: {op_type}")

            # 添加输出收集器（传入执行 ID）
            current_stream.sink(PlaygroundSink, execution_id=execution_id)

            # 执行 Pipeline
            logger.info("▶️ 开始执行 Pipeline...")
            try:
                env.submit(autostop=False)
            except Exception as submit_error:
                import traceback

                error_details = traceback.format_exc()
                logger.error(f"❌ 提交任务失败的详细错误: {submit_error}")
                logger.error(f"完整错误堆栈:\n{error_details}")
                raise

            # 等待执行完成（最多等待60秒，适应 LLM 调用）
            timeout = 60
            elapsed = 0
            results = None
            while elapsed < timeout:
                time.sleep(0.5)
                elapsed += 0.5
                results = PlaygroundSink.get_results(execution_id)
                if results:
                    logger.info(f"✅ 收到执行结果，等待时间: {elapsed:.1f}秒")
                    break

            # 检查是否超时
            if not results and elapsed >= timeout:
                logger.warning(f"⚠️ 等待结果超时 ({timeout}秒)，但可能执行仍在进行")

            # 停止环境
            env.close()

            execution_time = time.time() - start_time
            logger.info(f"✅ Pipeline 执行完成，耗时: {execution_time:.2f}秒")

            # 再次获取结果（防止在 close 前刚好完成）
            if not results:
                results = PlaygroundSink.get_results(execution_id)
                if results:
                    logger.info("✅ 在环境关闭后获取到结果")

            # 格式化结果
            output = self._format_results(results, user_input)

            # 清理结果
            PlaygroundSink.clear_results(execution_id)

            return {
                "output": output,
                "status": "completed",
                "results": results,
                "execution_time": execution_time,
                "logs": self.execution_logs,
            }

        except Exception as e:
            logger.error(f"❌ Pipeline 执行失败: {str(e)}")
            logger.error(traceback.format_exc())

            return {
                "output": f"❌ 执行失败: {str(e)}\n\n{traceback.format_exc()}",
                "status": "error",
                "results": [],
                "execution_time": 0,
                "logs": self.execution_logs,
            }

        finally:
            self._cleanup_logging()

    def _load_operator(self, operator_type: str):
        """加载操作符类"""
        try:
            # Source 节点（但在 Playground 中会被 PlaygroundSource 替代，所以这里跳过）
            if operator_type == "FileSource":
                logger.info("跳过 FileSource（已由 PlaygroundSource 替代）")
                return None

            # Sink 节点（但在 Playground 中会被 PlaygroundSink 替代，所以这里跳过）
            elif operator_type == "TerminalSink":
                logger.info("跳过 TerminalSink（已由 PlaygroundSink 替代）")
                return None

            # Retriever 节点
            elif operator_type == "ChromaRetriever":
                from sage.middleware.operators.rag import ChromaRetriever

                return ChromaRetriever

            elif operator_type == "SimpleRetriever":
                logger.warning("SimpleRetriever 暂未实现")
                return None

            # Generator 节点
            elif operator_type == "HFGenerator":
                from sage.middleware.operators.rag import HFGenerator

                return HFGenerator

            elif operator_type == "OpenAIGenerator":
                from sage.middleware.operators.rag import OpenAIGenerator

                return OpenAIGenerator

            # Promptor 节点
            elif operator_type == "QAPromptor":
                from sage.middleware.operators.rag import QAPromptor

                return QAPromptor

            # Reranker 节点
            elif operator_type == "LLMbased_Reranker" or operator_type == "LLMbasedReranker":
                from sage.middleware.operators.rag import LLMbased_Reranker

                return LLMbased_Reranker

            elif operator_type == "BGEReranker":
                from sage.middleware.operators.rag import BGEReranker

                return BGEReranker

            # Refiner 节点
            elif operator_type == "AbstractiveRecompRefiner":
                from sage.middleware.operators.rag import RefinerOperator

                return RefinerOperator

            elif operator_type == "SageLLMNode":
                # TODO: 接入 sageLLM gateway 推理算子
                # Issue URL: https://github.com/intellistream/SAGE/issues/1107
                raise ValueError("SageLLMNode 尚未实现：请通过 sageLLM gateway 接入推理服务")

            else:
                logger.warning(f"未知的操作符类型: {operator_type}")
                return None

        except ImportError as e:
            logger.error(f"无法导入操作符 {operator_type}: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _format_results(self, results: list, user_input: str) -> str:
        """格式化结果输出"""
        logger.info(f"🔍 开始格式化结果: 收到 {len(results) if results else 0} 个结果")
        if results:
            logger.info(f"📊 结果类型: {[type(r).__name__ for r in results]}")
            logger.info(f"📊 第一个结果内容: {results[0] if results else None}")

        if not results:
            return "⚠️ Pipeline 执行完成，但未返回结果"

        output_parts = [f"💬 查询: {user_input}\n", "=" * 60, ""]

        for idx, result in enumerate(results, start=1):
            if idx > 1:
                output_parts.append("")  # 结果之间空行

            output_parts.append(f"📋 结果 {idx}:")

            if isinstance(result, dict):
                # 处理字典结果
                for key, value in result.items():
                    if key == "retrieval_results" and isinstance(value, list):
                        # 特殊处理检索结果
                        output_parts.append(f"\n  ✅ 检索到 {len(value)} 个文档:")
                        for doc_idx, doc in enumerate(value[:5], start=1):  # 最多显示5个
                            if isinstance(doc, dict):
                                doc_text = doc.get("text", doc.get("content", str(doc)))
                            else:
                                doc_text = str(doc)
                            # 截断文本，避免过长
                            display_text = (
                                doc_text[:200] + "..." if len(doc_text) > 200 else doc_text
                            )
                            output_parts.append(f"\n  📄 文档 {doc_idx}:")
                            output_parts.append(f"    {display_text}")

                    elif key in ["answer", "response", "generated_text", "generated"]:
                        # 特殊处理生成的答案
                        output_parts.append("\n  💡 生成的答案:")
                        output_parts.append(f"    {value}")

                    elif key in ["query", "question"]:
                        # 跳过查询本身（已经在顶部显示）
                        continue

                    elif key in ["retrieve_time", "generate_time", "rerank_time"]:
                        # 显示性能指标
                        output_parts.append(f"\n  ⏱️ {key}: {value:.3f}秒")

                    else:
                        # 其他字段（跳过过长的字段）
                        if key not in ["question"]:  # 跳过嵌套的question字段
                            value_str = str(value)
                            if len(value_str) > 500:
                                value_str = value_str[:500] + "..."
                            output_parts.append(f"\n  {key}: {value_str}")
            else:
                # 非字典结果
                result_str = str(result)
                if len(result_str) > 500:
                    result_str = result_str[:500] + "..."
                output_parts.append(f"  {result_str}")

        output_parts.extend(["", "=" * 60, "✅ 执行完成"])

        return "\n".join(output_parts)


# 单例实例
_executor = PlaygroundExecutor()


def get_playground_executor() -> PlaygroundExecutor:
    """获取 Playground 执行器单例"""
    return _executor
