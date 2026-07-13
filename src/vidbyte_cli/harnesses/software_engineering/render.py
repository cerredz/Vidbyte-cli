"""Bespoke terminal output for software-engineering results (the optional `present` hook).

A harness only writes this when the default RunRenderer.render_status isn't good enough for
its results. Everything here is pure string formatting.
"""

from __future__ import annotations

from ...lib.harness.context import HarnessContext
from ...types.harness import HarnessRun


def render_fix_result(run: HarnessRun, ctx: HarnessContext) -> str:
    # Formats a `fix` run into a one-glance summary of what the harness did.
    result = run.result
    if result is None:
        return f"software-engineering: run {run.run_id} is {run.status}."
    lines = [f"software-engineering: run {run.run_id} {run.status}."]
    if result.summary:
        lines.append(result.summary)
    if result.branch:
        lines.append(f"  branch: {result.branch}")
    if result.pr_url:
        lines.append(f"  PR: {result.pr_url}")
    return "\n".join(lines)
