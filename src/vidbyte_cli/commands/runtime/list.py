"""`vidbyte-cli runtime list` renders locally executable runtime products.

The catalog comes from Vidbyte so price and supported host metadata stay aligned with the
paid admission route rather than becoming hard-coded command policy.
"""

from __future__ import annotations

import click
from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext


class RuntimeListCommand:
    """Lists the backend's runtime-only capability catalog."""

    def register(self, parent: click.Group) -> None:
        # Attaches the authenticated catalog read beneath the runtime group.
        @parent.command(name="list", help="List local runtime primitives and prices")
        @click.pass_obj
        def _run(context: ApplicationContext) -> None:
            # Delegates command behavior to the class-owned execution method.
            self.execute(context)

    def execute(self, context: ApplicationContext) -> None:
        # Fetches one bounded catalog and renders only its typed public fields.
        catalog = context.runtime_endpoints().list_capabilities()
        rows: list[JsonValue] = [
            capability.model_dump(mode="json") for capability in catalog.capabilities
        ]
        human_rows = []
        for item in catalog.capabilities:
            hosts = ", ".join(host.value for host in item.supported_hosts)
            price = item.admission_price_cents / 100
            human_rows.append(
                f"{item.capability_id}@{item.version}: ${price:.2f} per local launch ({hosts})"
            )
        human = "\n".join(human_rows)
        context.output().result(
            OutputDocument(
                kind="runtime.catalog",
                data={"capabilities": rows, "topup_path": catalog.topup_path},
            ),
            human or "No local runtime primitives are available.",
        )
