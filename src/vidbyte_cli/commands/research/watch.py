"""`vidbyte-cli research watch <run_id>` — follow one run until it settles.

The interval starts at ten seconds and backs off, which is a rate limit decision rather than
a taste one. The backend meters API keys on a weighted per-minute budget where starting a run
costs many times what reading one does, so a tight poll loop can exhaust the same budget the
caller needs to start their next run.

Only coarse transitions are reported. The status route publishes no live counters, so a
change is detected by fingerprinting exactly what it does publish.
"""

from __future__ import annotations

import time

import click

from ...lib.errors.failures import ResearchWatchTimedOut
from ...lib.runtime.context import ApplicationContext
from ...types.research import ResearchRunStatus
from .render import ResearchRenderer

_INITIAL_DELAY_SECONDS = 10.0
_MAXIMUM_DELAY_SECONDS = 60.0
_BACKOFF_FACTOR = 1.5
_MAXIMUM_TIMEOUT_SECONDS = 86_400.0


class ResearchWatchCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="watch", help="Watch one research run until it finishes")
        @click.argument("run_id")
        @click.option(
            "--timeout",
            type=click.FloatRange(1.0, _MAXIMUM_TIMEOUT_SECONDS),
            help="Give up waiting after this many seconds. The run keeps going.",
        )
        @click.pass_obj
        def _run(context: ApplicationContext, run_id: str, timeout: float | None) -> None:
            self.execute(context, run_id, timeout)

    def execute(self, context: ApplicationContext, run_id: str, timeout: float | None) -> None:
        # Polls to a terminal status, then emits that final snapshot as the one result.
        run = self._poll_until_terminal(context, run_id, timeout)
        rendered = ResearchRenderer().run_status(run)
        context.output().result(rendered.document, rendered.human)

    def _poll_until_terminal(
        self,
        context: ApplicationContext,
        run_id: str,
        timeout: float | None,
    ) -> ResearchRunStatus:
        # Always fetches once before honouring the deadline, so a tiny timeout still reports.
        endpoints = context.research_endpoints()
        renderer = ResearchRenderer()
        started = time.monotonic()
        delay = _INITIAL_DELAY_SECONDS
        last_fingerprint: str | None = None
        while True:
            run = endpoints.get_run(run_id)
            fingerprint = self._fingerprint(run)
            if fingerprint != last_fingerprint:
                self._emit_transition(context, renderer, run)
                last_fingerprint = fingerprint
            if run.status.is_terminal():
                return run
            if self._expired(started, timeout, delay):
                raise ResearchWatchTimedOut(run_id)
            time.sleep(delay)
            delay = self._next_delay(delay)

    def _fingerprint(self, run: ResearchRunStatus) -> str:
        # The whole of what the status route publishes, so no change can go unnoticed.
        return f"{run.status.value}:{run.phase}:{run.updated_at.isoformat()}"

    def _emit_transition(
        self,
        context: ApplicationContext,
        renderer: ResearchRenderer,
        run: ResearchRunStatus,
    ) -> None:
        # Progress goes to the transition channel so a single-JSON consumer still sees
        # exactly one document on stdout at the end.
        rendered = renderer.transition(run)
        context.output().transition(rendered.document, rendered.human)

    def _expired(self, started: float, timeout: float | None, delay: float) -> bool:
        # Checked before sleeping: waiting past the deadline to discover it would be worse.
        return timeout is not None and (time.monotonic() - started) + delay >= timeout

    def _next_delay(self, delay: float) -> float:
        return min(delay * _BACKOFF_FACTOR, _MAXIMUM_DELAY_SECONDS)
