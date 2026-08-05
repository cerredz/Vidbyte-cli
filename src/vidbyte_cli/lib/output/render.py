"""FILE: src/vidbyte_cli/lib/output/render.py

PURPOSE: Pure human rendering for generic harness run, list, and catalog DTOs.

ROLE IN CODEBASE: Commands pair these strings with versioned OutputDocuments. No stream,
transport, or terminal behavior exists here.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from ...types.harness import HarnessRun, HarnessSummary


class RunRenderer:
    """Compact stable human summaries for generic harness resources."""

    def render_status(self, run: HarnessRun) -> str:
        lines = [
            f"Run: {run.run_id}",
            f"Harness: {run.harness} / {run.command}",
            f"Status: {run.status}",
            f"Updated: {run.updated_at}",
        ]
        if run.events:
            lines.append("Events:")
            lines.extend(
                f"- {event.created_at} [{event.type}] {event.message}" for event in run.events
            )
        if run.result is not None:
            if run.result.summary:
                lines.append(f"Summary: {run.result.summary}")
            if run.result.pr_url:
                lines.append(f"Pull request: {run.result.pr_url}")
            if run.result.branch:
                lines.append(f"Branch: {run.result.branch}")
        return "\n".join(lines)

    def render_list(self, runs: list[HarnessRun]) -> str:
        if not runs:
            return "No harness runs found."
        lines = ["RUN ID  STATUS  HARNESS / COMMAND"]
        lines.extend(f"{run.run_id}  {run.status}  {run.harness} / {run.command}" for run in runs)
        return "\n".join(lines)

    def render_catalog(self, harnesses: list[HarnessSummary]) -> str:
        if not harnesses:
            return "No harnesses are currently available."
        lines = ["NAME  VERSION  DESCRIPTION"]
        lines.extend(
            f"{harness.name}  {harness.version}  {harness.description}" for harness in harnesses
        )
        return "\n".join(lines)
