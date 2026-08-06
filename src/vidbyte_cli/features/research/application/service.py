"""FILE: src/vidbyte_cli/features/research/application/service.py

PURPOSE: Orchestrates start, add, and resume mutations with one idempotency identity,
prompt-free journal record, gateway call, admission update, and optional watching.

ROLE IN CODEBASE: Click commands in PR 6 call this service. The HTTP gateway arrives only
in PR 7, keeping all persistent-thread and resume policy transport independent.

ARCHITECTURE NOTE: Resume sends no prompt and first verifies the current run is terminal
and resumable. Journal fingerprints are SHA-256 hashes, never request bodies.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from ....lib.errors.cli_error import CliError
from ....lib.errors.codes import CliErrorCode
from ..domain import ResearchGateway, ResearchRunAccepted, ResearchStatePolicy
from .models import ResearchMutationInput, ResearchMutationResult, ResearchResumeInput
from .ports import IdempotencyProvider, OperationRecorder
from .watcher import ResearchWatcher

_Mutation = Callable[[str], ResearchRunAccepted]


class ResearchService:
    """Persistent research mutation use cases."""

    def __init__(
        self,
        gateway: ResearchGateway,
        idempotency: IdempotencyProvider,
        journal: OperationRecorder,
        watcher: ResearchWatcher,
        state_policy: ResearchStatePolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._idempotency = idempotency
        self._journal = journal
        self._watcher = watcher
        self._states = state_policy or ResearchStatePolicy()

    def start(self, command: ResearchMutationInput) -> ResearchMutationResult:
        return self._mutate(
            "research start",
            command.idempotency_key,
            command.request.model_dump_json(),
            lambda key: self._gateway.start(command.request, key),
            command.wait,
            command.timeout_seconds,
        )

    def add(self, thread_id: str, command: ResearchMutationInput) -> ResearchMutationResult:
        self._require_id(thread_id, "thread")
        return self._mutate(
            f"research add {thread_id}",
            command.idempotency_key,
            f"{thread_id}:{command.request.model_dump_json()}",
            lambda key: self._gateway.add(thread_id, command.request, key),
            command.wait,
            command.timeout_seconds,
        )

    def resume(self, run_id: str, command: ResearchResumeInput) -> ResearchMutationResult:
        self._require_id(run_id, "run")
        current = self._gateway.get_run(run_id)
        if not self._states.is_resumable(current.status):
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                f"Research run '{run_id}' is not resumable from status '{current.status.value}'.",
                2,
            )
        return self._mutate(
            f"research resume {run_id}",
            command.idempotency_key,
            run_id,
            lambda key: self._gateway.resume(run_id, key),
            command.wait,
            command.timeout_seconds,
        )

    def _mutate(
        self,
        command_name: str,
        explicit_key: str | None,
        fingerprint_input: str,
        mutation: _Mutation,
        wait: bool,
        timeout_seconds: float | None,
    ) -> ResearchMutationResult:
        key = self._idempotency.create(explicit_key)
        fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
        self._journal.begin(
            key,
            command_name,
            key,
            fingerprint,
            f"Retry '{command_name}' with idempotency key {key}",
        )
        accepted = mutation(key)
        self._journal.accepted(
            key,
            accepted.run_id,
            f"vidbyte-cli research status {accepted.run_id}",
        )
        run = self._watcher.watch(accepted.run_id, timeout_seconds) if wait else None
        return ResearchMutationResult(
            accepted=accepted,
            idempotency_key=key,
            run=run,
        )

    def _require_id(self, value: str, label: str) -> None:
        if not 1 <= len(value) <= 200:
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                f"The {label} identifier is empty or too large.",
                2,
            )
