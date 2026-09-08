"""Typed HTTP operations for local-runtime discovery and paid admission.

No execution input crosses this boundary. The future executor will call admission only
after it knows that a supported native host can actually be launched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....types.runtime import (
    RuntimeAdmissionGrant as AdmissionGrant,
)
from ....types.runtime import (
    RuntimeAdmissionRequest as AdmissionRequest,
)
from ....types.runtime import (
    RuntimeCapabilityCatalog,
    RuntimeGrantVerificationRequest,
)
from ..client import ApiClient
from ..response import ResponseDecoder, ResponseShape

if TYPE_CHECKING:
    from ..runtime_payment import RuntimePayment

RUNTIME_CATALOG_PATH = "/api/x402/runtime"
ADVERSARIAL_TEAM_ADMISSION_PATH = "/api/x402/runtime/adversarial-team/admissions"
# Matches the capability declared in the backend x402 catalog (vidbyte PR #508), which
# names these routes "activate" rather than "admissions".
SAME_HOST_ENSEMBLE_ADMISSION_PATH = "/api/x402/runtime/same-host-ensemble/activate"
PERSISTENCE_ADMISSION_PATH = "/api/x402/runtime/persistence/activate"


class RuntimeEndpoints:
    """Runtime operations bound to one authenticated API client."""

    def __init__(self, client: ApiClient) -> None:
        # Retains the invocation-owned client without opening a connection.
        self._client = client

    def verify_grant(self, request: RuntimeGrantVerificationRequest) -> AdmissionGrant:
        # Authenticates the proof at the server without exposing its HMAC signing secret.
        return self._client.post(
            "/api/x402/runtime/grants/verify", request, AdmissionGrant, shape=ResponseShape.DIRECT
        )

    def list_capabilities(self) -> RuntimeCapabilityCatalog:
        # Reads the direct runtime-only catalog document.
        return self._client.get(
            RUNTIME_CATALOG_PATH, RuntimeCapabilityCatalog, shape=ResponseShape.DIRECT
        )

    def admit_adversarial_team(self, request: AdmissionRequest, key: str) -> AdmissionGrant:
        # Purchases one replay-safe local execution admission.
        return self._client.post(
            ADVERSARIAL_TEAM_ADMISSION_PATH,
            request,
            AdmissionGrant,
            shape=ResponseShape.DIRECT,
            idempotency_key=key,
        )

    def admit_same_host_ensemble(self, request: AdmissionRequest, key: str) -> AdmissionGrant:
        # Purchases one replay-safe local execution admission.
        return self._client.post(
            SAME_HOST_ENSEMBLE_ADMISSION_PATH,
            request,
            AdmissionGrant,
            shape=ResponseShape.DIRECT,
            idempotency_key=key,
        )

    def admit_persistence_x402(
        self, request: AdmissionRequest, key: str, payer: RuntimePayment
    ) -> AdmissionGrant:
        # The same receipt goes through database-backed online verification before launch.
        response = self._client.post_runtime_payment(
            PERSISTENCE_ADMISSION_PATH, request, key, payer
        )
        return ResponseDecoder().one(response, AdmissionGrant, ResponseShape.DIRECT)

    def admit_persistence(self, request: AdmissionRequest, key: str) -> AdmissionGrant:
        # Purchases one replay-safe local execution admission.
        return self._client.post(
            PERSISTENCE_ADMISSION_PATH,
            request,
            AdmissionGrant,
            shape=ResponseShape.DIRECT,
            idempotency_key=key,
        )
