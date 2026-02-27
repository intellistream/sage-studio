"""Studio port configuration.

Studio 独立端口配置，不依赖 SAGE sage-common。

Port Allocation Map
───────────────────────────────────────────────────────────────────────
Group 1 · Platform Services
  5173   FRONTEND          Vite dev server
  8765   BACKEND           Studio FastAPI backend
  8889   GATEWAY           sageLLM Gateway (OpenAI-compatible API)
  8899   EDGE_DEFAULT      sage-edge aggregator shell

Group 2 · sageLLM Inference Engine  (sage-llm serve --port SHELL --engine-port ENGINE)
  Each instance: ENGINE = SHELL + 1 (default)

  8901   SAGELLM_SERVE_PORT    sage-llm --port  (shell / proxy process)
  8902   SAGELLM_ENGINE_PORT   sage-llm --engine-port  (real vLLM engine)
  8903   SAGELLM_SERVE_PORT_2  second shell
  8904   SAGELLM_ENGINE_PORT_2 second real vLLM engine
  8001   LLM_DEFAULT           vLLM direct (non-WSL2, no shell wrapper)

Group 3 · Embedding Services
  8090   EMBEDDING_DEFAULT   Primary embedding server (e.g. BAAI/bge-*)
  8091   EMBEDDING_SECONDARY Secondary embedding instance

─── Backward-Compat Aliases ─────────────────────────────────────────
  BENCHMARK_LLM  = SAGELLM_SERVE_PORT (8901) — deprecated name, same port
───────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations


class StudioPorts:
    """Studio 服务端口配置 — all port numbers grouped by service category."""

    # =========================================================================
    # Group 1: Platform Services
    # =========================================================================
    FRONTEND = 5173           # Vite dev server
    FRONTEND_PREVIEW = 4173   # Vite preview build
    FRONTEND_DEV_EXTRA = (35180,)  # HMR / extra dev ports
    BACKEND = 8765            # Studio FastAPI backend (auth, flows, pipeline builder)
    GATEWAY = 8889            # sageLLM Gateway — primary OpenAI-compatible API entry
    EDGE_DEFAULT = 8899       # sage-edge aggregator

    # =========================================================================
    # Group 2: sageLLM Inference Engine
    #
    # `sage-llm serve` spawns:
    #   SHELL  — gateway + control-plane proxy  (--port SHELL)
    #   ENGINE — real vLLM / HF inference        (--engine-port ENGINE = SHELL + 1)
    # =========================================================================
    SAGELLM_SERVE_PORT = 8901     # sage-llm --port  (shell process, instance 1)
    SAGELLM_ENGINE_PORT = 8902    # sage-llm --engine-port  (real vLLM, instance 1)
    SAGELLM_SERVE_PORT_2 = 8903   # shell process, instance 2
    SAGELLM_ENGINE_PORT_2 = 8904  # real vLLM, instance 2
    LLM_DEFAULT = 8001            # vLLM direct port (non-WSL2, without shell wrapper)

    # =========================================================================
    # Group 3: Embedding Services
    # =========================================================================
    EMBEDDING_DEFAULT = 8090    # Primary embedding server (e.g. BAAI/bge-large-zh-v1.5)
    EMBEDDING_SECONDARY = 8091  # Secondary embedding instance

    # =========================================================================
    # Backward-compat aliases (deprecated — use the named constants above)
    # =========================================================================
    BENCHMARK_LLM = 8901         # Deprecated → SAGELLM_SERVE_PORT
    BENCHMARK_EMBEDDING = 8091   # Deprecated → EMBEDDING_SECONDARY
    LLM_WSL_FALLBACK = 8901      # Deprecated → SAGELLM_SERVE_PORT

    @classmethod
    def get_frontend_port(cls) -> int:
        """获取前端端口"""
        return cls.FRONTEND

    @classmethod
    def get_frontend_dev_ports(cls) -> list[int]:
        """获取前端开发相关端口列表"""
        return [cls.FRONTEND, cls.FRONTEND_PREVIEW, *cls.FRONTEND_DEV_EXTRA]

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
            return cls.SAGELLM_SERVE_PORT
        return cls.LLM_DEFAULT

    @classmethod
    def get_llm_probe_ports(cls) -> list[int]:
        """Ordered list of ports to probe when auto-detecting a running LLM engine."""
        return [cls.SAGELLM_SERVE_PORT, cls.SAGELLM_SERVE_PORT_2, cls.LLM_DEFAULT]

    @classmethod
    def get_embedding_ports(cls) -> list[int]:
        """Ordered list of ports to probe when auto-detecting a running embedding server."""
        return [cls.EMBEDDING_DEFAULT, cls.EMBEDDING_SECONDARY]
