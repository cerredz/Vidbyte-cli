"""Plans a rules scan into batches and runs those batches against the hosted rules agent.

The runner is the only code in this feature that spends money. Batches run one at a time so the
spend cap stays exact: before each batch it stops on the time limit or when the remaining budget
cannot cover the backend's admission floor, and each request caps its own cost at what is left.
A finished batch is written to disk before the manifest marks it complete, so a resume never
buys the same batch twice; a crash between the two is covered by the backend replaying the
stored response for the batch's fixed idempotency key.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from ...lib.api.endpoints.rules import RulesEndpoints
from ...lib.constants.rules import RulesBackendLimit
from ...lib.errors.cli_error import CliError
from ...lib.errors.codes import CliErrorCode
from ...types.rules import (
    RulesBatchRecord,
    RulesBatchRequest,
    RulesPromptPayload,
    RulesScanLimits,
    RulesScanManifest,
    RulesScanScope,
    RulesScanStatus,
    RulesStopReason,
)
from .store import RulesScanStore
from .transcripts import TranscriptPrompt


class RulesScanPlanner:
    """Turns a prompt selection into a stored, batched scan plan."""

    def plan(
        self,
        scan_id: str,
        scope: RulesScanScope,
        limits: RulesScanLimits,
        prompts: Sequence[TranscriptPrompt],
    ) -> RulesScanManifest:
        # Splits prompt IDs into batches of the configured size, keeping selection order.
        ids = [prompt.prompt_id for prompt in prompts]
        size = limits.batch_size
        now = datetime.now(UTC)
        return RulesScanManifest(
            scan_id=scan_id,
            created_at=now,
            updated_at=now,
            scope=scope,
            limits=limits,
            batches=[ids[start : start + size] for start in range(0, len(ids), size)],
        )


class RulesScanRunner:
    """Runs a scan's pending batches under its spend and time limits."""

    def __init__(
        self, endpoints: RulesEndpoints, store: RulesScanStore, progress: Callable[[str], None]
    ) -> None:
        # Progress lines go to stderr and never carry prompt text.
        self._endpoints = endpoints
        self._store = store
        self._progress = progress

    def run(
        self, manifest: RulesScanManifest, prompts_by_id: Mapping[str, TranscriptPrompt]
    ) -> RulesScanManifest:
        # Runs pending batches in order until done or a limit or failure stops the scan.
        started = time.monotonic()
        manifest.status, manifest.stop_reason = RulesScanStatus.RUNNING, None
        self._store.save_manifest(manifest)
        for index in manifest.pending_batches:
            stop = self._stop_reason_before_batch(manifest, started)
            if stop is not None:
                return self._stop(manifest, stop)
            prompts = [
                prompts_by_id[prompt_id]
                for prompt_id in manifest.batches[index]
                if prompt_id in prompts_by_id
            ]
            if not prompts:
                # Every prompt of this batch vanished from disk since planning; nothing to buy.
                self._complete_batch(manifest, index, charged_cents=0, rule_count=0)
                continue
            try:
                record = self._run_batch(manifest, index, prompts)
            except CliError as error:
                reason = (
                    RulesStopReason.CREDIT_EXHAUSTED
                    if error.code_value == CliErrorCode.CREDIT_EXHAUSTED.value
                    else RulesStopReason.BATCH_FAILED
                )
                self._progress(f"batch {index + 1}/{len(manifest.batches)} failed: {error.message}")
                return self._stop(manifest, reason)
            self._store.save_batch(manifest.scan_id, record)
            self._complete_batch(
                manifest,
                index,
                charged_cents=record.result.charged_cents,
                rule_count=len(record.result.rules),
            )
            self._progress(
                f"batch {index + 1}/{len(manifest.batches)}: "
                f"{len(record.result.flagged_prompt_ids)} flagged, "
                f"{len(record.result.rules)} rules, {record.result.charged_cents}c (total "
                f"{manifest.spent_cents}c)"
            )
        manifest.status = RulesScanStatus.COMPLETED
        self._store.save_manifest(manifest)
        return manifest

    def _stop_reason_before_batch(
        self, manifest: RulesScanManifest, started: float
    ) -> RulesStopReason | None:
        # Time first, then money: an expired scan should not spend another cent.
        limits = manifest.limits
        if (
            limits.time_limit_seconds is not None
            and time.monotonic() - started >= limits.time_limit_seconds
        ):
            return RulesStopReason.TIME_LIMIT
        if self._batch_budget(manifest) < RulesBackendLimit.MIN_BATCH_COST_CENTS:
            return RulesStopReason.SPEND_LIMIT
        return None

    @staticmethod
    def _batch_budget(manifest: RulesScanManifest) -> int:
        # What the next batch may spend: the per-batch cap, bounded by the remaining scan budget.
        remaining = manifest.limits.max_spend_cents - manifest.spent_cents
        return min(manifest.limits.max_batch_cost_cents, remaining)

    def _run_batch(
        self, manifest: RulesScanManifest, index: int, prompts: Sequence[TranscriptPrompt]
    ) -> RulesBatchRecord:
        # Buys one batch under a key fixed by scan and position, so any retry is a replay.
        self._progress(f"batch {index + 1}/{len(manifest.batches)}: sending {len(prompts)} prompts")
        request = RulesBatchRequest(
            scan_id=manifest.scan_id,
            batch_index=index,
            max_cost_cents=self._batch_budget(manifest),
            prompts=[self._payload(prompt) for prompt in prompts],
        )
        result = self._endpoints.run_batch(request, f"rules-{manifest.scan_id}-{index:04d}")
        return RulesBatchRecord(batch_index=index, completed_at=datetime.now(UTC), result=result)

    @staticmethod
    def _payload(prompt: TranscriptPrompt) -> RulesPromptPayload:
        # Clamps every field to the backend's bounds so one long paste or path never fails a batch.
        return RulesPromptPayload(
            prompt_id=prompt.prompt_id,
            host=prompt.host,
            session_id=prompt.session_id[: RulesBackendLimit.SESSION_ID_MAX_CHARS],
            text=prompt.text[: RulesBackendLimit.PROMPT_MAX_CHARS],
            project=prompt.project[: RulesBackendLimit.PROJECT_MAX_CHARS]
            if prompt.project
            else None,
            created_at=prompt.created_at,
        )

    def _complete_batch(
        self, manifest: RulesScanManifest, index: int, *, charged_cents: int, rule_count: int
    ) -> None:
        # Records progress durably before the next batch can start.
        manifest.completed_batches = sorted({*manifest.completed_batches, index})
        manifest.spent_cents += charged_cents
        manifest.rule_count += rule_count
        self._store.save_manifest(manifest)

    def _stop(self, manifest: RulesScanManifest, reason: RulesStopReason) -> RulesScanManifest:
        # Saves a stopped scan with its reason so resume and list can report it.
        manifest.status, manifest.stop_reason = RulesScanStatus.STOPPED, reason
        self._store.save_manifest(manifest)
        return manifest
