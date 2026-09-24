"""Typed wrapper for the hosted rules agent's one paid route.

`POST /api/x402/runtime/rules/batches` classifies one batch of prompts with Jev, writes rules
from the flagged ones, and settles the batch's metered usage against the API wallet. The route
returns its DTO directly, and every call carries an idempotency key so a retried request is a
replay rather than a second purchase.
"""

from __future__ import annotations

from ....lib.constants.rules import RULES_BATCH_PATH
from ....types.rules import RulesBatchRequest, RulesBatchResult
from ..client import ApiClient
from ..response import ResponseShape


class RulesEndpoints:
    """Rules-agent operations bound to one authenticated, long-timeout API client."""

    def __init__(self, client: ApiClient) -> None:
        # Binds the endpoint group to a client whose timeout covers a hosted batch.
        self._client = client

    def run_batch(self, request: RulesBatchRequest, key: str) -> RulesBatchResult:
        # Buys and runs one batch; the key is fixed per scan and batch position.
        return self._client.post(
            RULES_BATCH_PATH,
            request,
            RulesBatchResult,
            shape=ResponseShape.DIRECT,
            idempotency_key=key,
        )
