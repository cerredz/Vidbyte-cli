"""Explicitly pay the Vidbyte API-balance top-up challenge."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import click

from ...lib.api.endpoints.billing import TOP_UP_CENTS
from ...lib.errors.failures import BillingTopUpApprovalRequired
from ...lib.output import OutputDocument

if TYPE_CHECKING:
    from ...lib.runtime.context import ApplicationContext

_TOP_UP_HELP = (
    "Purchase the minimum Vidbyte API balance through the authenticated API key. "
    "The command sends a paid x402 challenge and credits the same account that made "
    "the failed operation. "
    "Run it only after the user has approved the charge and the signer environment is configured. "
    "The result reports the credited amount and the balance available for the original retry."
)
_CONFIRM_HELP = (
    "Authorize this paid API-balance purchase only after the user approves it. "
    "The flag is required because handling an error must never create an automatic "
    "financial side effect. "
    "Without this flag the command stops before resolving credentials, creating a "
    "signer, or sending HTTP. "
    "Do not set it unless the user understands that the minimum top-up is five US dollars."
)
_IDEMPOTENCY_KEY_HELP = (
    "Provide the idempotency key used for a top-up whose result is uncertain. "
    "Leave this option unset for a new purchase so the command creates one fresh key. "
    "Reuse a prior key only when recovering the same request after a timeout or lost response. "
    "Do not change the key while retrying because that could create a second charge."
)


class BillingTopUpCommand:
    """Registers the one explicit command that can purchase API balance."""

    def register(self, parent: click.Group) -> None:
        # Keeps payment behind an explicit confirmation flag and never runs from error handling.
        @parent.command(name="top-up", help=_TOP_UP_HELP)
        @click.option(
            "--confirm",
            is_flag=True,
            help=_CONFIRM_HELP,
        )
        @click.option(
            "--idempotency-key",
            default=None,
            help=_IDEMPOTENCY_KEY_HELP,
        )
        @click.pass_obj
        def _run(context: ApplicationContext, confirm: bool, idempotency_key: str | None) -> None:
            # Routes parsed Click options through the typed command boundary.
            self.execute(context, confirm, idempotency_key)

    def execute(
        self, context: ApplicationContext, confirm: bool, idempotency_key: str | None
    ) -> None:
        # Validates approval before resolving credentials or creating a payment authorization.
        if not confirm:
            raise BillingTopUpApprovalRequired()
        from ...lib.api.runtime_payment import RuntimePayment

        payer = RuntimePayment(context.environment, TOP_UP_CENTS)
        result = context.billing_endpoints().top_up(idempotency_key or str(uuid4()), payer)
        context.output().result(
            OutputDocument(kind="billing.top_up", data=result.model_dump(mode="json")),
            self._summary(result.credited_cents, result.available_balance_cents, result.rail),
        )

    @staticmethod
    def _summary(credited_cents: int, available_balance_cents: int, rail: str) -> str:
        # Reports only non-secret financial outcome fields returned by the backend.
        return (
            f"Added ${credited_cents / 100:.2f} to Vidbyte API balance via {rail}. "
            f"Available balance: ${available_balance_cents / 100:.2f}."
        )
