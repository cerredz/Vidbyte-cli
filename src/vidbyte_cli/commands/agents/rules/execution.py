"""The paid part of `scan` and `resume`: run pending batches, write the document, report.

Both verbs reach this only after every input was validated and the prompts were read locally,
so credentials are resolved here and nowhere earlier. A stopped scan still writes its document
from the batches that finished and prints its full result, with a warning naming the stop reason
and the command that continues it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ....lib.runtime.context import ApplicationContext
from ....services.rules.document import RulesDocumentRenderer
from ....services.rules.runner import RulesScanRunner
from ....services.rules.store import RulesScanStore
from ....services.rules.transcripts import TranscriptPrompt
from ....types.rules import RulesScanManifest, RulesScanStatus
from .render import RulesRenderer


class RulesScanExecution:
    """Runs a stored scan's pending batches and publishes its rules document."""

    def __init__(self, context: ApplicationContext, store: RulesScanStore) -> None:
        # Binds the invocation context and the scan store both verbs share.
        self._context = context
        self._store = store

    def run(
        self,
        manifest: RulesScanManifest,
        prompts_by_id: Mapping[str, TranscriptPrompt],
        out: Path | None,
    ) -> None:
        # Spends, records, renders, and reports one scan run.
        output = self._context.output()
        runner = RulesScanRunner(self._context.rules_endpoints(), self._store, output.diagnostic)
        manifest = runner.run(manifest, prompts_by_id)
        self.publish(manifest, out)
        if manifest.status is RulesScanStatus.STOPPED and manifest.stop_reason is not None:
            output.warning(
                f"Scan stopped early ({manifest.stop_reason.value}). Continue with: "
                f"{RulesRenderer.resume_command(manifest)}"
            )

    def publish(self, manifest: RulesScanManifest, out: Path | None) -> None:
        # Writes rules.md from every recorded batch, stores its path, and prints the result.
        records = self._store.load_batches(manifest)
        body = RulesDocumentRenderer().render(manifest, records)
        manifest.document_path = str(self._store.write_document(manifest.scan_id, body, out))
        self._store.save_manifest(manifest)
        rules = [rule for record in records for rule in record.result.rules]
        rendered = RulesRenderer().scan(manifest, self._store.scan_dir(manifest.scan_id), rules)
        self._context.output().result(rendered.document, rendered.human)
