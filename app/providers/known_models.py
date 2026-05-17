"""Built-in provider catalog — port of `PROVIDERS` from source server.js:447-667.

Each entry mirrors the source verbatim: provider id → {name, env_key,
auth_profile_provider, known_models[]}. Custom providers do not appear here;
they live as files under `/opt/openclaw/config/<id>.json`.

The OpenAI-compatible providers all use Bearer `/v1/models` for key validation
(see `key_tester.test_bearer_models`).
"""

from __future__ import annotations

from typing import Final, TypedDict


class _Model(TypedDict, total=False):
    id: str
    name: str
    default: bool


class _ProviderEntry(TypedDict, total=False):
    name: str
    env_key: str | None
    auth_profile_provider: str
    known_models: list[_Model]
    test_url: str | None
    test_method: str  # bearer_models | google_key_query | anthropic | zhipu | none
    oauth_only: bool


def _bearer(name: str, env_key: str, test_url: str) -> _ProviderEntry:
    """Helper for OpenAI-compatible providers — Bearer GET /v1/models test."""
    slug = env_key.replace("_API_KEY", "").lower()
    return {
        "name": name,
        "env_key": env_key,
        "auth_profile_provider": slug,
        "known_models": [],
        "test_url": test_url,
        "test_method": "bearer_models",
    }


PROVIDERS: Final[dict[str, _ProviderEntry]] = {
    "anthropic": {
        "name": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "auth_profile_provider": "anthropic",
        "known_models": [
            {"id": "claude-opus-4-6", "name": "Claude Opus 4.6"},
            {"id": "claude-sonnet-4-6-20260218", "name": "Claude Sonnet 4.6"},
            {"id": "claude-opus-4-5-20251101", "name": "Claude Opus 4.5"},
            {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5"},
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
        ],
        "test_url": "https://api.anthropic.com/v1/messages",
        "test_method": "anthropic",
    },
    "openai": {
        "name": "OpenAI (API Key)",
        "env_key": "OPENAI_API_KEY",
        "auth_profile_provider": "openai",
        "known_models": [
            {"id": "gpt-5.4", "name": "GPT-5.4"},
            {"id": "gpt-5.4-pro-2026-03-05", "name": "GPT-5.4 Pro"},
            {"id": "gpt-5-mini", "name": "GPT-5 Mini"},
            {"id": "gpt-4.1", "name": "GPT-4.1"},
            {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini"},
            {"id": "gpt-4.1-nano", "name": "GPT-4.1 Nano"},
            {"id": "o3", "name": "o3"},
            {"id": "o3-pro", "name": "o3 Pro"},
            {"id": "o3-mini", "name": "o3 Mini"},
            {"id": "o4-mini", "name": "o4-mini"},
        ],
        "test_url": "https://api.openai.com/v1/models",
        "test_method": "bearer_models",
    },
    "openai-codex": {
        "name": "ChatGPT OAuth (Codex)",
        "env_key": None,
        "auth_profile_provider": "openai-codex",
        "oauth_only": True,
        "known_models": [
            {"id": "openai-codex/gpt-5.4", "name": "GPT-5.4", "default": True},
            {"id": "openai-codex/gpt-5.4-mini", "name": "GPT-5.4-Mini"},
            {"id": "openai-codex/gpt-5.3-codex", "name": "GPT-5.3-Codex"},
            {"id": "openai-codex/gpt-5.3-codex-spark", "name": "GPT-5.3-Codex-Spark"},
            {"id": "openai-codex/gpt-5.2-codex", "name": "GPT-5.2-Codex"},
            {"id": "openai-codex/gpt-5.2", "name": "GPT-5.2"},
            {"id": "openai-codex/gpt-5.1-codex-max", "name": "GPT-5.1-Codex-Max"},
            {"id": "openai-codex/gpt-5.1-codex-mini", "name": "GPT-5.1-Codex-Mini"},
            {"id": "openai-codex/gpt-5.1", "name": "GPT-5.1"},
        ],
        "test_method": "none",
    },
    "google": {
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "auth_profile_provider": "google",
        "known_models": [
            {"id": "gemini-3.1-pro-preview", "name": "Gemini 3.1 Pro Preview"},
            {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash Preview"},
            {"id": "gemini-3.1-flash-lite-preview", "name": "Gemini 3.1 Flash-Lite Preview"},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
            {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite"},
        ],
        "test_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "test_method": "google_key_query",
    },
    "deepseek": _bearer("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1/models"),
    "groq": _bearer("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/models"),
    "together": _bearer(
        "Together AI", "TOGETHER_API_KEY", "https://api.together.xyz/v1/models"
    ),
    "mistral": _bearer("Mistral AI", "MISTRAL_API_KEY", "https://api.mistral.ai/v1/models"),
    "xai": _bearer("xAI (Grok)", "XAI_API_KEY", "https://api.x.ai/v1/models"),
    "cerebras": _bearer("Cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/models"),
    "sambanova": _bearer(
        "SambaNova", "SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1/models"
    ),
    "fireworks": _bearer(
        "Fireworks AI", "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1/models"
    ),
    "cohere": _bearer(
        "Cohere", "COHERE_API_KEY", "https://api.cohere.ai/compatibility/v1/models"
    ),
    "yi": _bearer("Yi/01.AI", "YI_API_KEY", "https://api.01.ai/v1/models"),
    "baichuan": _bearer(
        "Baichuan AI", "BAICHUAN_API_KEY", "https://api.baichuan-ai.com/v1/models"
    ),
    "stepfun": _bearer("Stepfun", "STEPFUN_API_KEY", "https://api.stepfun.com/v1/models"),
    "siliconflow": _bearer(
        "SiliconFlow", "SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1/models"
    ),
    "novita": _bearer(
        "Novita AI", "NOVITA_API_KEY", "https://api.novita.ai/v3/openai/models"
    ),
    "openrouter": _bearer(
        "OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/models"
    ),
    "minimax": _bearer("Minimax", "MINIMAX_API_KEY", "https://api.minimax.io/v1/models"),
    "moonshot": _bearer(
        "Moonshot/Kimi", "MOONSHOT_API_KEY", "https://api.moonshot.ai/v1/models"
    ),
    "zhipu": {
        "name": "Zhipu/GLM",
        "env_key": "ZHIPU_API_KEY",
        "auth_profile_provider": "zhipu",
        "known_models": [],
        "test_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "test_method": "zhipu",
    },
}


def list_builtin_ids() -> tuple[str, ...]:
    return tuple(PROVIDERS.keys())


def get(provider_id: str) -> _ProviderEntry | None:
    return PROVIDERS.get(provider_id)


def env_key_for(provider_id: str) -> str | None:
    p = PROVIDERS.get(provider_id)
    return p.get("env_key") if p else None
