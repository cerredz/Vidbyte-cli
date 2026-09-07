"""Deterministic receipt policy shared by offline and authenticated online verification."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ...types.runtime import RuntimeAdmissionCheck as Check
from ...types.runtime import RuntimeAdmissionGrant as Grant
from ...types.runtime import RuntimeAdmissionVerdict as Verdict
from ...types.runtime import RuntimeLaunchPlan as Plan
from ..constants.runtime import AdmissionReason as Reason
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
        check = self._check_policy(plan, grant, current)
        if check.passed and grant is not None:
            check = self._check_signature(grant, current, key)
        return self._verdict(plan, grant, check)

    def verify_online(self, plan: Plan, grant: Grant, verified: Grant) -> Verdict:
        # The endpoint supplies the canonical receipt after checking signature and ownership.
        check = self._check_policy(plan, grant, datetime.now(UTC))
        if grant != verified:
            check = Check(Reason.RECEIPT_MISMATCH)
        return self._verdict(plan, grant, check)

    def _check_policy(self, plan: Plan, grant: Grant | None, now: datetime) -> Check:
        # Rejects unknown products, price drift and unbounded receipt lifetimes.
        if grant is None:
            return Check(Reason.MISSING)
        if grant.capability_id != plan.capability_id:
            return Check(Reason.CAPABILITY_MISMATCH)
        if grant.charged_cents != _ALLOWED_PRICES.get(grant.capability_id):
            return Check(Reason.PRICE_MISMATCH)
        if not grant.admission_id.strip() or grant.execution_location != "local":
            return Check(Reason.LOCATION_OR_ID_INVALID)
        if not grant.grant_token:
            return Check(Reason.TOKEN_MISSING)
        return self._check_time(grant, now)

    def _check_time(self, grant: Grant, now: datetime) -> Check:
        # Both timestamps must be aware, current and bounded independently of token claims.
        start, end = grant.admitted_at, grant.expires_at
        if end is None or start.tzinfo is None or end.tzinfo is None or now.tzinfo is None:
            return Check(Reason.TIME_INVALID)
        if end <= now:
            return Check(Reason.EXPIRED)
        if start > now or end <= start:
            return Check(Reason.TIME_INVALID)
        if (end - start).total_seconds() > _MAX_TTL_SECONDS:
            return Check(Reason.TTL_INVALID)
        return Check(Reason.PASSED)

    def _check_signature(self, grant: Grant, now: datetime, key: str | None) -> Check:
        # A valid token must bind every public signed field to this receipt.
        if not key or not key.strip():
            return Check(Reason.VERIFICATION_KEY_MISSING)
        try:
            signed = self._verifier.verify(grant.grant_token or "", key, now)
        except ValueError:
            return Check(Reason.SIGNATURE_INVALID)
        matches = (
            signed.admission_id == grant.admission_id,
            f"{signed.capability_id}@{signed.version}" == grant.capability_id,
            signed.charged_cents == grant.charged_cents,
            signed.admitted_at == grant.admitted_at,
            signed.expires_at == grant.expires_at,
        )
        return Check(Reason.PASSED if all(matches) else Reason.SIGNED_CLAIMS_MISMATCH)

    def _verdict(self, plan: Plan, grant: Grant | None, check: Check) -> Verdict:
        # Exposes safe policy metadata without the token or caller identity.
        return Verdict(
            admitted=check.passed,
            admission_id=grant.admission_id if grant else "rta_missing",
            capability_id=plan.capability_id,
            reason=None if check.passed else check.reason.value,
        )

    @staticmethod
    def hash_idempotency_key(key: str) -> str:
        # Binds the invocation without transmitting its raw key to verification.
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
