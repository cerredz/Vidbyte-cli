"""Authenticated billing operations exposed by the Vidbyte API."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from ....types.api import BillingTopUpResult
from ....types.runtime import RuntimeAdmissionRequest, RuntimeHost
from ..client import ApiClient
from ..response import ResponseDecoder, ResponseShape

if TYPE_CHECKING:
    from ..runtime_payment import RuntimePayment

TOP_UP_PATH = "/agent/topup"
TOP_UP_CENTS = 500


class BillingEndpoints:
    """Billing operations bound to one authenticated API client."""

    def __init__(self, client: ApiClient) -> None:
        # Retains the invocation-owned client without opening a connection.
        self._client = client

    def top_up(self, key: str | None, payer: RuntimePayment) -> BillingTopUpResult:
        # Pays one exact top-up challenge and validates the credited balance response.
        idempotency_key = key or str(uuid4())
        response = self._client.post_runtime_payment(
            TOP_UP_PATH,
            RuntimeAdmissionRequest(host=RuntimeHost.CODEX),
            idempotency_key,
            payer,
        )
        return ResponseDecoder().one(response, BillingTopUpResult, ResponseShape.DIRECT)
