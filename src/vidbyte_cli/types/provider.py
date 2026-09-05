"""Provider identity for BYOK runtime execution.

Defines the closed set of providers a user can bring their own key for,
plus probe and environment mappings. No networking or storage here.
"""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    """Every external provider this CLI can store a key for."""

    OPENAI = "openai"
    CLAUDE = "claude"
    GROK = "grok"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MUSE = "muse"


PROVIDER_KEY_PREFIXES: dict[Provider, tuple[str, ...]] = {
    Provider.OPENAI: ("sk-",),
    Provider.CLAUDE: ("sk-ant-",),
    Provider.GROK: (),
    Provider.DEEPSEEK: ("sk-",),
    Provider.GLM: (),
    Provider.MUSE: ("LLM|",),
}

PROVIDER_ENV_VARS: dict[Provider, str] = {
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.CLAUDE: "ANTHROPIC_API_KEY",
    Provider.GROK: "XAI_API_KEY",
    Provider.DEEPSEEK: "DEEPSEEK_API_KEY",
    Provider.GLM: "ZAI_API_KEY",
    Provider.MUSE: "MODEL_API_KEY",
}

PROVIDER_DISPLAY: dict[Provider, str] = {
    Provider.OPENAI: "OpenAI",
    Provider.CLAUDE: "Claude",
    Provider.GROK: "Grok",
    Provider.DEEPSEEK: "DeepSeek",
    Provider.GLM: "GLM",
    Provider.MUSE: "Muse",
}

PROVIDER_PROBE_URLS: dict[Provider, str] = {
    Provider.OPENAI: "https://api.openai.com/v1/models",
    Provider.CLAUDE: "https://api.anthropic.com/v1/models",
    Provider.GROK: "https://api.x.ai/v1/models",
    Provider.DEEPSEEK: "https://api.deepseek.com/v1/models",
    Provider.GLM: "https://api.z.ai/api/paas/v4/models",
    Provider.MUSE: "https://api.meta.ai/v1/models",
}
