"""Deterministic hierarchical gate that must admit before any local agent runs."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from ...types.runtime import RuntimeAdmissionGrant, RuntimeAdmissionVerdict, RuntimeLaunchPlan
from .verification import RuntimeGrantVerifier

_ALLOWED_PRICES: dict[str, int] = {"runtime.review.adversarial-team@1": 25, "runtime.same-host-ensemble@1": 2}


class RuntimeAdmissionGate:
    """Three-layer deterministic gate whose only caller is the command layer."""

    def __init__(self, verifier: RuntimeGrantVerifier | None = None) -> None:
        # Uses the shared verifier so signature checks are identical everywhere.
        self._verifier = verifier or RuntimeGrantVerifier()

    def verify(self, plan: RuntimeLaunchPlan, grant: RuntimeAdmissionGrant | None, now: datetime | None, verification_key: str | None, allow_list: tuple[str, ...] | None = None) -> RuntimeAdmissionVerdict:
        # Runs Layer 1 then Layer 2 then optional Layer 3, failing closed at the first rejection.
        current = now or datetime.now(timezone.utc)
        allowed = allow_list or tuple(_ALLOWED_PRICES.keys())
        layer1 = self.verify_layer1_typed_grant(plan, grant, allowed)
        if not layer1.admitted:
            return layer1
        layer2 = self.verify_layer2_signature(grant, current, verification_key)
        if not layer2.admitted:
            return layer2
        return RuntimeAdmissionVerdict(admitted=True, admission_id=grant.admission_id, capability_id=grant.capability_id, reason=None)

    def verify_layer1_typed_grant(self, plan: RuntimeLaunchPlan, grant: RuntimeAdmissionGrant | None, allow_list: tuple[str, ...]) -> RuntimeAdmissionVerdict:
        # Asserts exact field-by-field equality without trusting model or prompt strings.
        if grant is None:
            return RuntimeAdmissionVerdict(admitted=False, admission_id="rta_missing", capability_id=plan.capability_id, reason="grant_missing")
        if grant.capability_id != plan.capability_id:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_capability_mismatch")
        if grant.capability_id not in allow_list:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_capability_not_allowed")
        expected_price = _ALLOWED_PRICES.get(grant.capability_id)
        if expected_price is not None and grant.charged_cents != expected_price:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_price_mismatch")
        if grant.execution_location != "local":
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_location_invalid")
        if grant.admitted_at.tzinfo is None:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_time_not_tz_aware")
        return RuntimeAdmissionVerdict(admitted=True, admission_id=grant.admission_id, capability_id=grant.capability_id, reason=None)

    def verify_layer2_signature(self, grant: RuntimeAdmissionGrant | None, now: datetime, verification_key: str | None) -> RuntimeAdmissionVerdict:
        # Verifies the backend's HMAC and bounded expiry without a network round trip.
        if grant is None or grant.grant_token is None:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id if grant else "rta_missing", capability_id=grant.capability_id if grant else "unknown", reason="grant_token_missing")
        if grant.expires_at is not None and grant.expires_at.tzinfo is None:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_expiry_not_tz_aware")
        if grant.expires_at is not None and grant.expires_at <= now:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_expired")
        if grant.expires_at is not None and grant.expires_at <= grant.admitted_at:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_expiry_before_admission")
        if verification_key is None or not verification_key.strip():
            # No key configured means the local HMAC check is intentionally skipped; Layer 1 already gates.
            return RuntimeAdmissionVerdict(admitted=True, admission_id=grant.admission_id, capability_id=grant.capability_id, reason=None)
        try:
            self._verifier.verify(grant.grant_token, verification_key, now)
        except Exception:
            return RuntimeAdmissionVerdict(admitted=False, admission_id=grant.admission_id, capability_id=grant.capability_id, reason="grant_signature_invalid")
        return RuntimeAdmissionVerdict(admitted=True, admission_id=grant.admission_id, capability_id=grant.capability_id, reason=None)

    @staticmethod
    def hash_idempotency_key(key: str) -> str:
        # Hashes the raw Idempotency-Key so it never appears in logs or tokens raw.
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
