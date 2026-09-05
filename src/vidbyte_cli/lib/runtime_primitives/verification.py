"""Offline HMAC verification for runtime admission grant_token values."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime

_MAX_PAYLOAD_BYTES = 4096


class RuntimeGrantVerifier:
    """Verifies base64url(payload).base64url(hmac) tokens issued by vidbyte."""

    def verify(self, token: str, signing_key: str, now: datetime) -> dict:
        # Splits, decodes, constant-time compares, and checks expiry on the decoded payload.
        if not isinstance(token, str) or "." not in token:
            raise ValueError("Invalid grant token format.")
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("Invalid grant token format.")
        payload_b64, sig_b64 = parts
        try:
            payload_bytes = self._b64url_decode(payload_b64)
            sig_bytes = self._b64url_decode(sig_b64)
        except Exception as error:
            raise ValueError("Invalid grant token encoding.") from error
        if len(payload_bytes) > _MAX_PAYLOAD_BYTES:
            raise ValueError("Grant token payload too large.")
        expected = hmac.new(signing_key.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, sig_bytes):
            raise ValueError("Grant token signature invalid.")
        try:
            raw = json.loads(payload_bytes.decode("utf-8"))
        except Exception as error:
            raise ValueError("Grant token payload is not valid JSON.") from error
        if not isinstance(raw, dict):
            raise ValueError("Grant token payload must be an object.")
        expires_raw = raw.get("expires_at")
        if expires_raw is not None:
            try:
                from datetime import timezone

                exp = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            except Exception as error:
                raise ValueError("Grant token expiry is not a valid datetime.") from error
            if exp.tzinfo is None:
                raise ValueError("Grant token expiry must be timezone-aware.")
            if exp <= now:
                raise ValueError("Grant token has expired.")
        return raw

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        # Decodes base64url without padding, validating the input before decoding.
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
