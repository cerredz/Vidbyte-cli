"""Deterministic receipt policy shared by offline and authenticated online verification."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ...types.runtime import RuntimeAdmissionGrant as Grant
from ...types.runtime import RuntimeAdmissionVerdict as Verdict
from ...types.runtime import RuntimeLaunchPlan as Plan
from .verification import RuntimeGrantVerifier

_ALLOWED_PRICES = {
    "runtime.review.adversarial-team@1": 25,
    "runtime.adversarial-team@1": 25,
    "runtime.same-host-ensemble@1": 2,
    "runtime.persistence@1": 2,
}
_MAX_TTL_SECONDS = 3600
Key = str | None


class RuntimeAdmissionGate:
    """Checks local policy after a cryptographic verification boundary."""

    def __init__(self, verifier: RuntimeGrantVerifier | None = None) -> None:
        # Shares the strict payload decoder with offline verification.
        self._verifier = verifier or RuntimeGrantVerifier()

    def verify(self, plan: Plan, grant: Grant | None, now: datetime | None, key: Key) -> Verdict:
        # Offline callers must supply a key; CLI execution uses backend verification.
        current = now or datetime.now(UTC)
        reason = self._policy_reason(plan, grant, current)
        if reason is None and grant is not None:
            reason = self._signature_reason(grant, current, key)
        return self._verdict(plan, grant, reason)

    def verify_online(self, plan: Plan, grant: Grant, verified: Grant) -> Verdict:
        # The endpoint supplies the canonical receipt after checking signature and ownership.
        reason = self._policy_reason(plan, grant, datetime.now(UTC))
        if grant != verified:
            reason = "grant_receipt_mismatch"
        return self._verdict(plan, grant, reason)

    def _policy_reason(self, plan: Plan, grant: Grant | None, now: datetime) -> str | None:
        # Rejects unknown products, price drift and unbounded receipt lifetimes.
        if grant is None:
            return "grant_missing"
        if grant.capability_id != plan.capability_id:
            return "grant_capability_mismatch"
        if grant.charged_cents != _ALLOWED_PRICES.get(grant.capability_id):
            return "grant_price_mismatch"
        if not grant.admission_id.strip() or grant.execution_location != "local":
            return "grant_location_or_id_invalid"
        if not grant.grant_token:
            return "grant_token_missing"
        return self._time_reason(grant, now)

    def _time_reason(self, grant: Grant, now: datetime) -> str | None:
        # Both timestamps must be aware, current and bounded independently of token claims.
        start, end = grant.admitted_at, grant.expires_at
        if end is None or start.tzinfo is None or end.tzinfo is None or now.tzinfo is None:
            return "grant_time_invalid"
        if end <= now:
            return "grant_expired"
        if start > now or end <= start:
            return "grant_time_invalid"
        if (end - start).total_seconds() > _MAX_TTL_SECONDS:
            return "grant_ttl_invalid"
        return None

    def _signature_reason(self, grant: Grant, now: datetime, key: str | None) -> str | None:
        # A valid token must bind every public signed field to this receipt.
        if not key or not key.strip():
            return "grant_verification_key_missing"
        try:
            signed = self._verifier.verify(grant.grant_token or "", key, now)
        except ValueError:
            return "grant_signature_invalid"
        matches = (
            signed.admission_id == grant.admission_id,
            f"{signed.capability_id}@{signed.version}" == grant.capability_id,
            signed.charged_cents == grant.charged_cents,
            signed.admitted_at == grant.admitted_at,
            signed.expires_at == grant.expires_at,
        )
        return None if all(matches) else "grant_signed_claims_mismatch"

    def _verdict(self, plan: Plan, grant: Grant | None, reason: str | None) -> Verdict:
        # Exposes safe policy metadata without the token or caller identity.
        return Verdict(
            admitted=reason is None,
            admission_id=grant.admission_id if grant else "rta_missing",
            capability_id=plan.capability_id,
            reason=reason,
        )

    @staticmethod
    def hash_idempotency_key(key: str) -> str:
        # Binds the invocation without transmitting its raw key to verification.
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
