"""Studio port configuration.

Studio 独立端口配置，不依赖 SAGE sage-common。
"""

from __future__ import annotations


class StudioPorts:
    """Studio 服务端口配置"""

    # Frontend (Vite dev server)
    FRONTEND = 5173

    # Backend (FastAPI)
    BACKEND = 8080

    # Gateway (来自 sagellm，Studio 依赖的外部服务)
    GATEWAY = 8889

    # LLM 推理服务端口
    LLM_DEFAULT = 8001  # sageLLM 默认端口
    LLM_WSL_FALLBACK = 8901  # WSL2 备用端口
    BENCHMARK_LLM = 8901  # Benchmark 专用

    # Embedding 服务端口
    EMBEDDING_DEFAULT = 8090
    BENCHMARK_EMBEDDING = 8091

    @classmethod
    def get_frontend_port(cls) -> int:
        """获取前端端口"""
        return cls.FRONTEND

    @classmethod
    def get_backend_port(cls) -> int:
        """获取后端端口"""
        return cls.BACKEND

    @classmethod
    def get_gateway_port(cls) -> int:
        """获取 Gateway 端口"""
        return cls.GATEWAY

    @classmethod
    def get_recommended_llm_port(cls) -> int:
        """获取推荐的 LLM 端口（自动检测 WSL2）"""
        import platform
        if "microsoft" in platform.uname().release.lower():
            return cls.LLM_WSL_FALLBACK
        return cls.LLM_DEFAULT
