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


PROVIDER_KEY_PREFIXES: dict[Provider, tuple[str, ...]] = {
    Provider.OPENAI: ("sk-",),
    Provider.CLAUDE: ("sk-ant-",),
}

PROVIDER_ENV_VARS: dict[Provider, str] = {
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.CLAUDE: "ANTHROPIC_API_KEY",
}

PROVIDER_DISPLAY: dict[Provider, str] = {
    Provider.OPENAI: "OpenAI",
    Provider.CLAUDE: "Claude",
}

PROVIDER_PROBE_URLS: dict[Provider, str] = {
    Provider.OPENAI: "https://api.openai.com/v1/models",
    Provider.CLAUDE: "https://api.anthropic.com/v1/models",
}
