"""Human text and machine documents for every rules-agent result.

Both encodings are built together so they cannot drift. Every scan result carries the scan ID,
the absolute scan folder, the document path, and a ready-to-paste resume command whenever work
remains, because the heaviest callers of this CLI are agents with no transcript to look back on.
No renderer here ever prints prompt text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from ....lib.constants.rules import RULES_DEFAULT_SINCE, RulesBackendLimit, RulesCap, RulesDefault
from ....lib.output import OutputDocument
from ....services.rules.transcripts import TranscriptSession, TranscriptSource
from ....types.rules import Rule, RulesScanManifest, RulesScanStatus


@dataclass(frozen=True)
class RenderedResult:
    """One result in both encodings the output manager may be asked for."""

    document: OutputDocument
    human: str


class RulesRenderer:
    """Presentation for scans, sources, sessions, limits, and stored documents."""

    def scan(
        self, manifest: RulesScanManifest, scan_dir: Path, rules: Sequence[Rule]
    ) -> RenderedResult:
        # A finished, stopped, or planned scan with its continuation when work remains.
        resume = self.resume_command(manifest)
        data: dict[str, JsonValue] = {
            "scan_id": manifest.scan_id,
            "scan_dir": str(scan_dir),
            "document_path": manifest.document_path,
            "status": manifest.status.value,
            "stop_reason": manifest.stop_reason.value if manifest.stop_reason else None,
            "prompt_count": manifest.prompt_count,
            "batches_total": len(manifest.batches),
            "batches_completed": len(manifest.completed_batches),
            "spent_cents": manifest.spent_cents,
            "max_spend_cents": manifest.limits.max_spend_cents,
            "rule_count": len(rules),
            "rules": [rule.model_dump(mode="json") for rule in rules],
            "resume": resume,
        }
        lines = [
            f"Scan:      {manifest.scan_id} "
            f"({manifest.status.value}"
            f"{', ' + manifest.stop_reason.value if manifest.stop_reason else ''})",
            f"Batches:   {len(manifest.completed_batches)}/{len(manifest.batches)} "
            f"({manifest.prompt_count} prompts planned)",
            f"Spent:     ${manifest.spent_cents / 100:.2f} of "
            f"${manifest.limits.max_spend_cents / 100:.2f}",
            f"Rules:     {len(rules)}",
            f"Document:  {manifest.document_path or '(not written yet)'}",
            f"Folder:    {scan_dir}",
        ]
        lines += [f"  - {rule.title}: {rule.rule}" for rule in rules[:10]]
        if len(rules) > 10:
            lines.append(f"  ... {len(rules) - 10} more in the document")
        if resume:
            lines += ["", f"Continue:  {resume}"]
        return RenderedResult(OutputDocument(kind="rules.scan", data=data), "\n".join(lines))

    @staticmethod
    def resume_command(manifest: RulesScanManifest) -> str | None:
        # A paste-ready continuation, only when a stored scan still has batches to run.
        if manifest.status is RulesScanStatus.COMPLETED or not manifest.pending_batches:
            return None
        return f"vidbyte-cli agents rules resume {manifest.scan_id}"

    def hosts(
        self, sources: Sequence[TranscriptSource], counts: dict[str, tuple[int, str | None]]
    ) -> RenderedResult:
        # One row per supported host: where it keeps transcripts and what is there.
        rows: list[JsonValue] = []
        lines = []
        for source in sources:
            sessions, newest = counts.get(source.host.value, (0, None))
            root = source.root()
            rows.append(
                {
                    "host": source.host.value,
                    "root": str(root),
                    "exists": root.is_dir(),
                    "sessions": sessions,
                    "newest": newest,
                }
            )
            lines.append(
                f"{source.host.value:<9} {'found  ' if root.is_dir() else 'missing'} "
                f"{sessions:>5} sessions  newest {newest or '-':<25} {root}"
            )
        return RenderedResult(
            OutputDocument(kind="rules.hosts", data={"hosts": rows}), "\n".join(lines)
        )

    def sessions(self, sessions: Sequence[TranscriptSession]) -> RenderedResult:
        # The sessions a scope selects, newest first, with their prompt counts.
        rows: list[JsonValue] = [
            {
                "host": session.host.value,
                "session_id": session.session_id,
                "project": session.project,
                "latest_at": session.latest_at.isoformat() if session.latest_at else None,
                "prompt_count": len(session.prompts),
            }
            for session in sessions
        ]
        total = sum(len(session.prompts) for session in sessions)
        lines = [
            f"{session.host.value:<9} "
            f"{self._minute(session):<26} {len(session.prompts):>4} prompts  "
            f"{session.project or '-'}"
            for session in sessions
        ]
        lines += ["", f"{len(sessions)} sessions, {total} prompts"]
        return RenderedResult(
            OutputDocument(
                kind="rules.sessions",
                data={"sessions": rows, "session_count": len(sessions), "prompt_count": total},
            ),
            "\n".join(lines),
        )

    @staticmethod
    def _minute(session: TranscriptSession) -> str:
        # The session's latest activity to the minute, or a dash when unknown.
        return session.latest_at.isoformat(timespec="minutes") if session.latest_at else "-"

    def limits(self) -> RenderedResult:
        # Every default and hard cap a scan is subject to.
        data: dict[str, JsonValue] = {
            "default_since": RULES_DEFAULT_SINCE,
            "default_max_spend_cents": int(RulesDefault.MAX_SPEND_CENTS),
            "max_spend_cap_cents": int(RulesCap.MAX_SPEND_CENTS),
            "default_max_batch_cost_cents": int(RulesDefault.MAX_BATCH_COST_CENTS),
            "backend_max_batch_cost_cents": int(RulesBackendLimit.MAX_BATCH_COST_CENTS),
            "default_batch_size": int(RulesDefault.BATCH_SIZE),
            "backend_batch_max_prompts": int(RulesBackendLimit.BATCH_MAX_PROMPTS),
            "backend_prompt_max_chars": int(RulesBackendLimit.PROMPT_MAX_CHARS),
            "backend_min_batch_cost_cents": int(RulesBackendLimit.MIN_BATCH_COST_CENTS),
            "time_limit_cap_seconds": int(RulesCap.TIME_LIMIT_SECONDS),
            "max_sessions_cap": int(RulesCap.MAX_SESSIONS),
            "max_prompts_cap": int(RulesCap.MAX_PROMPTS),
        }
        human = "\n".join(
            (
                f"--since           default {RULES_DEFAULT_SINCE}",
                f"--max-spend       default ${RulesDefault.MAX_SPEND_CENTS / 100:.2f}, cap "
                f"${RulesCap.MAX_SPEND_CENTS / 100:.2f}",
                f"--max-batch-cost  default ${RulesDefault.MAX_BATCH_COST_CENTS / 100:.2f}, "
                f"backend cap ${RulesBackendLimit.MAX_BATCH_COST_CENTS / 100:.2f}",
                f"--batch-size      default {RulesDefault.BATCH_SIZE}, max "
                f"{RulesBackendLimit.BATCH_MAX_PROMPTS}",
                f"--time-limit      no default, cap {RulesCap.TIME_LIMIT_SECONDS // 3600}h",
                f"--max-sessions    no default, cap {RulesCap.MAX_SESSIONS}",
                f"--max-prompts     no default, cap {RulesCap.MAX_PROMPTS}",
                f"Each prompt is truncated to {RulesBackendLimit.PROMPT_MAX_CHARS} characters.",
                f"A batch needs at least ${RulesBackendLimit.MIN_BATCH_COST_CENTS / 100:.2f} of "
                "wallet balance and remaining budget to start.",
            )
        )
        return RenderedResult(OutputDocument(kind="rules.limits", data=data), human)

    def scans(self, manifests: Sequence[RulesScanManifest]) -> RenderedResult:
        # Stored scans, newest first.
        rows: list[JsonValue] = [
            {
                "scan_id": item.scan_id,
                "created_at": item.created_at.isoformat(),
                "status": item.status.value,
                "stop_reason": item.stop_reason.value if item.stop_reason else None,
                "batches_completed": len(item.completed_batches),
                "batches_total": len(item.batches),
                "spent_cents": item.spent_cents,
                "rule_count": item.rule_count,
            }
            for item in manifests
        ]
        lines = [
            f"{item.scan_id}  {item.created_at.isoformat(timespec='minutes')}  "
            f"{item.status.value:<9} {len(item.completed_batches)}/{len(item.batches)} batches  "
            f"${item.spent_cents / 100:.2f}  {item.rule_count} rules"
            for item in manifests
        ] or ["No rules scans are stored yet."]
        return RenderedResult(
            OutputDocument(kind="rules.scans", data={"scans": rows}), "\n".join(lines)
        )

    def show(
        self, manifest: RulesScanManifest, body: str | None, rules: Sequence[Rule]
    ) -> RenderedResult:
        # The stored document for humans, the structured rules for machines.
        data: dict[str, JsonValue] = {
            "scan_id": manifest.scan_id,
            "status": manifest.status.value,
            "document_path": manifest.document_path,
            "rules": [rule.model_dump(mode="json") for rule in rules],
        }
        return RenderedResult(
            OutputDocument(kind="rules.document", data=data),
            body or "This scan has no rules document yet.",
        )
