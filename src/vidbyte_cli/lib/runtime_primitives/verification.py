"""Strict offline verification for server-issued runtime receipts.

The execution flow verifies on the backend so its HMAC secret stays private.
This verifier remains for trusted integrations and contract diagnostics.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_MAX_PAYLOAD_BYTES = 4096
_MAX_TOKEN_CHARACTERS = 8192
_MAX_TTL_SECONDS = 3600


class SignedRuntimeGrant(BaseModel):
    """The complete signed payload; unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    admission_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    api_key_id: str = Field(min_length=1)
    charged_cents: int = Field(ge=1)
    idempotency_key_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    admitted_at: datetime
    expires_at: datetime


class RuntimeGrantVerifier:
    """Verifies exact HMAC framing and parses a bounded, fully typed payload."""

    def verify(self, token: str, signing_key: str, now: datetime) -> SignedRuntimeGrant:
        # Size bounds precede decode; all time and identity fields are mandatory.
        if not signing_key.strip() or len(token) > _MAX_TOKEN_CHARACTERS:
            raise ValueError("Grant key missing or token too large.")
        parts = token.split(".")
        if len(parts) != 2 or len(parts[0]) > ((_MAX_PAYLOAD_BYTES + 2) // 3) * 4:
            raise ValueError("Grant token malformed or payload too large.")
        payload = self._decode(parts[0])
        signature = self._decode(parts[1])
        expected = hmac.new(signing_key.encode("utf-8"), payload, hashlib.sha256).digest()
        if len(payload) > _MAX_PAYLOAD_BYTES or not hmac.compare_digest(expected, signature):
            raise ValueError("Grant signature invalid or payload too large.")
        parsed = SignedRuntimeGrant.model_validate_json(payload)
        self._validate_time(parsed, now)
        return parsed

    def _validate_time(self, grant: SignedRuntimeGrant, now: datetime) -> None:
        # Rejects absent timezones, future issuance, expiry and excessive lifetime.
        start, end = grant.admitted_at, grant.expires_at
        if start.tzinfo is None or end.tzinfo is None or now.tzinfo is None:
            raise ValueError("Grant time must be timezone-aware.")
        if not start <= now < end or (end - start).total_seconds() > _MAX_TTL_SECONDS:
            raise ValueError("Grant time is invalid or expired.")

    def _decode(self, value: str) -> bytes:
        # Strict decoding rejects whitespace and characters ignored by permissive decoders.
        try:
            return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        except (ValueError, UnicodeError) as error:
            raise ValueError("Invalid grant token encoding.") from error
