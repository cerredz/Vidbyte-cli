"""Canonical values for admission checks and persistent Codex execution.

Commands and the persistence adapter share progress copy; gate checks share reasons.
Provider credentials and model prompts never belong in this module.
"""

from enum import IntEnum, StrEnum


class AdmissionReason(StrEnum):
    """Closed vocabulary for local receipt checks, with explicit success."""

    PASSED = "passed"
    MISSING = "grant_missing"
    CAPABILITY_MISMATCH = "grant_capability_mismatch"
    PRICE_MISMATCH = "grant_price_mismatch"
    LOCATION_OR_ID_INVALID = "grant_location_or_id_invalid"
    TOKEN_MISSING = "grant_token_missing"
    TIME_INVALID = "grant_time_invalid"
    EXPIRED = "grant_expired"
    TTL_INVALID = "grant_ttl_invalid"
    VERIFICATION_KEY_MISSING = "grant_verification_key_missing"
    SIGNATURE_INVALID = "grant_signature_invalid"
    SIGNED_CLAIMS_MISMATCH = "grant_signed_claims_mismatch"
    RECEIPT_MISMATCH = "grant_receipt_mismatch"


class PersistenceLimit(IntEnum):
    """Execution bounds independent of the agent's answer content."""

    TURN_TIMEOUT_SECONDS = 3600


class PersistenceCodexConfig(StrEnum):
    """Child-only provider configuration; no native login state is changed."""

    PROVIDER = 'model_provider="vidbyte_openai"'
    NAME = 'model_providers.vidbyte_openai.name="OpenAI"'
    BASE_URL = 'model_providers.vidbyte_openai.base_url="https://api.openai.com/v1"'
    ENV_KEY = 'model_providers.vidbyte_openai.env_key="OPENAI_API_KEY"'
    WIRE_API = 'model_providers.vidbyte_openai.wire_api="responses"'


class PersistenceProgress(StrEnum):
    """Product-facing milestones; continuation copy describes intent, not observed work."""

    PREPARING = "Preparing your task and checking that Codex can run in this working directory."
    CREDENTIALS = "Loading your OpenAI credentials to run the task with your own API account."
    ADMISSION = "Requesting the two-cent Vidbyte admission for this persistence session."
    VERIFYING = "Verifying your admission receipt before starting work on your task."
    ADMITTED = "Your admission is verified. Preparing Codex to work on your task."
    STARTING = "Starting your original task in Codex, with your request preserved exactly."
    INITIAL_COMPLETE = (
        "Codex has returned its first response. Continuing in the same conversation "
        "to give it more opportunities to improve the result."
    )
    EARLY = (
        "Asking Codex to build on its work and look for ways to better satisfy your original task."
    )
    MIDDLE = (
        "Continuing the same task with another request to revisit gaps and strengthen the result."
    )
    LATE = "Giving Codex more time to refine its work while keeping your original request in view."
    FINAL = "Requesting the final improvement pass before returning the result to you."
    COMPLETE = "Codex has completed the requested persistence passes. Returning its final response."
