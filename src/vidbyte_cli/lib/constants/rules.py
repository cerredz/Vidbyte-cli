"""Canonical bounds and defaults for the rules agent.

The backend bounds mirror `backend/lib/config/runtime_rules.py` in the Vidbyte repository; the
server still validates them, so a drift here fails a request loudly instead of overspending.
Prompt text and credentials never belong in this module.
"""

from enum import IntEnum

RULES_BATCH_PATH = "/api/x402/runtime/rules/batches"
RULES_SCAN_ID_PREFIX = "rs"
RULES_DEFAULT_SINCE = "30d"


class RulesBackendLimit(IntEnum):
    """Bounds the hosted rules batch route enforces on every request."""

    BATCH_MAX_PROMPTS = 20
    PROMPT_MAX_CHARS = 6000
    ADMISSION_FLOOR_CENTS = 10
    MAX_BATCH_COST_CENTS = 500


class RulesDefault(IntEnum):
    """CLI defaults a caller can override per scan."""

    MAX_SPEND_CENTS = 200
    MAX_BATCH_COST_CENTS = 50
    BATCH_SIZE = 20
    REQUEST_TIMEOUT_SECONDS = 180
    LIST_LIMIT = 20


class RulesCap(IntEnum):
    """Hard ceilings on caller-supplied limits, independent of the backend's bounds."""

    MAX_SPEND_CENTS = 10_000
    MAX_SESSIONS = 10_000
    MAX_PROMPTS = 50_000
    TIME_LIMIT_SECONDS = 24 * 60 * 60
