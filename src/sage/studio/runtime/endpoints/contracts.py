from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EndpointProvider(str, Enum):
    ALIBABA_DASHSCOPE = "alibaba_dashscope"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    GROQ = "groq"
    AZURE_OPENAI = "azure_openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass(slots=True, frozen=True)
class EndpointProviderPreset:
    provider: EndpointProvider
    display_name: str
    default_base_url: str
    default_model_ids: tuple[str, ...]
    default_extra_headers: tuple[tuple[str, str], ...]
    requires_api_key: bool
    notes: str


@dataclass(slots=True, frozen=True)
class ManagedEndpoint:
    endpoint_id: str
    provider: EndpointProvider
    display_name: str
    base_url: str
    model_ids: tuple[str, ...] = ()
    enabled: bool = True
    is_default: bool = False
    extra_headers: tuple[tuple[str, str], ...] = ()
    api_key: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True, frozen=True)
class EndpointCreate:
    endpoint_id: str
    provider: EndpointProvider
    display_name: str
    base_url: str
    model_ids: tuple[str, ...] = ()
    enabled: bool = True
    is_default: bool = False
    extra_headers: tuple[tuple[str, str], ...] = ()
    api_key: str | None = None


@dataclass(slots=True, frozen=True)
class EndpointUpdate:
    display_name: str | None = None
    base_url: str | None = None
    model_ids: tuple[str, ...] | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    extra_headers: tuple[tuple[str, str], ...] | None = None
    replace_api_key: bool = False
    api_key: str | None = None


PROVIDER_PRESETS: tuple[EndpointProviderPreset, ...] = (
    EndpointProviderPreset(
        provider=EndpointProvider.ALIBABA_DASHSCOPE,
        display_name="Alibaba DashScope",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        default_model_ids=("qwen-plus", "qwen-max", "qwen-turbo"),
        default_extra_headers=(),
        requires_api_key=True,
        notes="Qwen models via OpenAI-compatible chat.completions API",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.OPENAI,
        display_name="OpenAI",
        default_base_url="https://api.openai.com/v1",
        default_model_ids=("gpt-4.1-mini", "gpt-4o-mini", "o3-mini"),
        default_extra_headers=(),
        requires_api_key=True,
        notes="Chat/Responses compatible",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.ANTHROPIC,
        display_name="Anthropic",
        default_base_url="https://api.anthropic.com/v1",
        default_model_ids=("claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"),
        default_extra_headers=(("anthropic-version", "2023-06-01"),),
        requires_api_key=True,
        notes="Messages API",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.OPENROUTER,
        display_name="OpenRouter",
        default_base_url="https://openrouter.ai/api/v1",
        default_model_ids=("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"),
        default_extra_headers=(),
        requires_api_key=True,
        notes="OpenAI-compatible proxy",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.GROQ,
        display_name="Groq",
        default_base_url="https://api.groq.com/openai/v1",
        default_model_ids=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        default_extra_headers=(),
        requires_api_key=True,
        notes="OpenAI-compatible low-latency",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.AZURE_OPENAI,
        display_name="Azure OpenAI",
        default_base_url="https://YOUR_RESOURCE.openai.azure.com",
        default_model_ids=("gpt-4o-mini",),
        default_extra_headers=(("api-version", "2024-08-01-preview"),),
        requires_api_key=True,
        notes="Requires deployment + api-version in request layer",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.GEMINI,
        display_name="Google Gemini",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model_ids=("gemini-2.0-flash", "gemini-1.5-pro"),
        default_extra_headers=(),
        requires_api_key=True,
        notes="Gemini REST endpoint",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.OLLAMA,
        display_name="Ollama",
        default_base_url="http://localhost:11434/v1",
        default_model_ids=("llama3.1:8b", "qwen2.5:7b"),
        default_extra_headers=(),
        requires_api_key=False,
        notes="Local runtime (OpenAI-compatible mode)",
    ),
    EndpointProviderPreset(
        provider=EndpointProvider.OPENAI_COMPATIBLE,
        display_name="Custom OpenAI-compatible",
        default_base_url="http://localhost:8000/v1",
        default_model_ids=("model-1",),
        default_extra_headers=(),
        requires_api_key=False,
        notes="sageLLM/LM Studio/TGI gateways",
    ),
)


__all__ = [
    "EndpointCreate",
    "EndpointProvider",
    "EndpointProviderPreset",
    "EndpointUpdate",
    "ManagedEndpoint",
    "PROVIDER_PRESETS",
]
