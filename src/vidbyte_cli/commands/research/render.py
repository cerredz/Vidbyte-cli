"""Human text and machine documents for every research result shape.

Both encodings are produced together so they cannot drift: a field added to the JSON without
a line in the human block is the failure mode this file exists to prevent.

The only thread identifier that appears anywhere here is `thread_id`, which the models bound
to the API's public share token. The backend's internal identifier never reaches this layer,
so no rendered line can offer a value a user would be unable to paste back.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from ...lib.output import OutputDocument
from ...types.research import (
    ResearchPortfolioPage,
    ResearchRunAccepted,
    ResearchRunStatus,
    ResearchThreadDetail,
    ResearchThreadSummary,
)


@dataclass(frozen=True)
class RenderedResult:
    """One result in both encodings the output manager may be asked for."""

    document: OutputDocument
    human: str


class ResearchRenderer:
    """Presentation for the four shapes the research surface returns."""

    def accepted(self, accepted: ResearchRunAccepted, idempotency_key: str) -> RenderedResult:
        # Admission: the two identifiers the caller needs for every follow-up command.
        data: dict[str, JsonValue] = {
            "thread_id": accepted.thread_id,
            "run_id": accepted.run_id,
            "status": accepted.status.value,
            "idempotency_key": idempotency_key,
        }
        human = "\n".join(
            (
                f"Thread:  {accepted.thread_id}",
                f"Run:     {accepted.run_id}",
                f"Status:  {accepted.status.value}",
                "",
                f"Watch it:    vidbyte-cli research watch {accepted.run_id}",
                f'Add to it:   vidbyte-cli research add {accepted.thread_id} "..."',
            )
        )
        return RenderedResult(OutputDocument(kind="research.run_accepted", data=data), human)

    def run_status(self, run: ResearchRunStatus) -> RenderedResult:
        # One run's coarse progress. The status route publishes no live counters.
        data: dict[str, JsonValue] = {
            "run_id": run.run_id,
            "status": run.status.value,
            "phase": run.phase,
            "continuation_count": run.continuation_count,
            "updated_at": run.updated_at.isoformat(),
            "terminal": run.status.is_terminal(),
        }
        human = "\n".join(
            (
                f"Run:      {run.run_id}",
                f"Status:   {run.status.value}",
                f"Phase:    {run.phase}",
                f"Continued: {run.continuation_count}",
                f"Updated:  {run.updated_at.isoformat()}",
            )
        )
        return RenderedResult(OutputDocument(kind="research.run_status", data=data), human)

    def transition(self, run: ResearchRunStatus) -> RenderedResult:
        # A progress line during watch; the same record, marked as not-yet-final.
        rendered = self.run_status(run)
        document = OutputDocument(kind="research.run_transition", data=rendered.document.data)
        return RenderedResult(document, f"{run.status.value} - {run.phase}")

    def thread(self, thread: ResearchThreadDetail) -> RenderedResult:
        # One thread read on its own, including the two fields a portfolio row omits.
        data = self._thread_fields(thread)
        data["latest_run_phase"] = thread.latest_run_phase
        data["favorite"] = thread.favorite
        human = "\n".join(
            (
                f"Thread:    {thread.thread_id}",
                f"Title:     {thread.title}",
                f"Runs:      {thread.run_count}",
                f"Sources:   {thread.source_count}",
                f"Artifacts: {thread.artifact_count}",
                f"Latest:    {self._latest(thread)}",
                f"Updated:   {thread.updated_at.isoformat()}",
            )
        )
        return RenderedResult(OutputDocument(kind="research.thread", data=data), human)

    def thread_page(self, page: ResearchPortfolioPage) -> RenderedResult:
        # One page of threads, plus the cursor that continues it when there is more.
        rows: list[JsonValue] = [self._thread_fields(thread) for thread in page.threads]
        data: dict[str, JsonValue] = {"threads": rows, "next_cursor": page.next_cursor}
        return RenderedResult(
            OutputDocument(kind="research.threads", data=data),
            self._thread_page_text(page),
        )

    def _thread_page_text(self, page: ResearchPortfolioPage) -> str:
        if not page.threads:
            return "No research threads."
        width = max(len(thread.thread_id) for thread in page.threads)
        lines = [
            f"{thread.thread_id.ljust(width)}  {thread.run_count:>4} runs  {thread.title}"
            for thread in page.threads
        ]
        if page.next_cursor is not None:
            lines.append("")
            lines.append(f"More available: --cursor {page.next_cursor}")
        return "\n".join(lines)

    def _thread_fields(self, thread: ResearchThreadSummary) -> dict[str, JsonValue]:
        # The row shape shared by the portfolio page and the single-thread read.
        status = thread.latest_run_status
        return {
            "thread_id": thread.thread_id,
            "title": thread.title,
            "run_count": thread.run_count,
            "source_count": thread.source_count,
            "artifact_count": thread.artifact_count,
            "latest_run_id": thread.latest_run_id,
            "latest_run_status": status.value if status is not None else None,
            "created_at": thread.created_at.isoformat(),
            "updated_at": thread.updated_at.isoformat(),
        }

    def _latest(self, thread: ResearchThreadSummary) -> str:
        # A thread whose runs were all deleted still reads, so both fields may be absent.
        if thread.latest_run_id is None:
            return "no runs"
        status = thread.latest_run_status
        return f"{thread.latest_run_id} ({status.value if status is not None else 'unknown'})"
