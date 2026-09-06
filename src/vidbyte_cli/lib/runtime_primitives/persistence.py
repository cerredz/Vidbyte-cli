"""Runs one Codex session for a fixed number of local continuation turns.

Task text travels on stdin; provider credentials stay in the child environment.
Only parsed final agent text escapes this adapter. Raw host diagnostics are never echoed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import TextIO, cast
from uuid import UUID

from ...types.runtime import PersistenceResult, PersistenceSettings
from ...types.runtime import RuntimeLaunchPlan as Plan
from ..errors.failures import PersistenceHostFailed

_MAX_EVENT_CHARACTERS = 1_048_576
_TURN_TIMEOUT_SECONDS = 3600
_CODEX_CONFIG = (
    'model_provider="vidbyte_openai"',
    'model_providers.vidbyte_openai.name="OpenAI"',
    'model_providers.vidbyte_openai.base_url="https://api.openai.com/v1"',
    'model_providers.vidbyte_openai.env_key="OPENAI_API_KEY"',
    'model_providers.vidbyte_openai.wire_api="responses"',
)


class PersistentCodexSession:
    """Owns child environment, process lifecycle and one explicit Codex session."""

    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None:
        # Copies invocation state without changing the parent environment or native login.
        self._environment = dict(environment)
        self._progress = progress

    def run(self, plan: Plan, settings: PersistenceSettings) -> PersistenceResult:
        # The fixed loop never asks the model whether it is done.
        template = files(__package__).joinpath("continuation.md").read_text(encoding="utf-8")
        continuation = template.replace("{{original_task}}", plan.task)
        self._progress("Persistence: running the original task.")
        session_id, text = self._turn(plan, plan.task, None)
        for index in range(settings.repeat_count):
            self._progress(f"Persistence: continuation {index + 1}/{settings.repeat_count}.")
            session_id, text = self._turn(plan, continuation, session_id)
        return PersistenceResult(
            session_id=session_id, continuation_turns=settings.repeat_count, text=text
        )

    def _arguments(self, plan: Plan, session_id: str | None) -> list[str]:
        # Prompts never enter shell arguments; resume targets only our validated session ID.
        arguments = [str(plan.executable), "exec", "--sandbox", "workspace-write"]
        for setting in _CODEX_CONFIG:
            arguments.extend(("-c", setting))
        if session_id is not None:
            arguments.extend(("resume", session_id))
        arguments.extend(("--json", "--skip-git-repo-check", "-"))
        return arguments

    def _turn(self, plan: Plan, prompt: str, session_id: str | None) -> tuple[str, str]:
        # Spools event output to disk so tool logs cannot exhaust process memory.
        arguments = self._arguments(plan, session_id)
        try:
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as events:
                self._execute(arguments, plan.working_directory, prompt, cast(TextIO, events))
                events.seek(0)
                return self._parse_events(cast(TextIO, events), session_id)
        except (OSError, UnicodeError, subprocess.SubprocessError) as error:
            raise PersistenceHostFailed() from error

    def _execute(self, arguments: list[str], cwd: Path, prompt: str, events: TextIO) -> None:
        # Cancels and reaps the entire child tree rather than leaving agents behind.
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
        with subprocess.Popen(
            arguments,
            cwd=cwd,
            env=self._environment,
            stdin=subprocess.PIPE,
            stdout=events,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            start_new_session=os.name != "nt",
        ) as process:
            try:
                process.communicate(prompt.encode("utf-8"), timeout=_TURN_TIMEOUT_SECONDS)
            except BaseException:
                self._stop(process)
                raise
            if process.returncode:
                raise PersistenceHostFailed()

    def _stop(self, process: subprocess.Popen[bytes]) -> None:
        # Stops descendants too, then reaps the owned process on cancellation or timeout.
        if process.poll() is None:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.kill()
        process.wait()

    def _parse_events(self, events: TextIO, session_id: str | None) -> tuple[str, str]:
        # Validates protocol completion independently of the model's answer content.
        completed, final_text = False, None
        while line := events.readline(_MAX_EVENT_CHARACTERS + 1):
            if len(line) > _MAX_EVENT_CHARACTERS:
                raise PersistenceHostFailed()
            event = self._event(line)
            kind = event.get("type")
            if kind == "thread.started":
                session_id = self._session_id(event.get("thread_id"), session_id)
            elif kind == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    final_text = item.get("text")
            elif kind in ("turn.failed", "error"):
                raise PersistenceHostFailed()
            elif kind == "turn.completed":
                completed = True
        if not completed or session_id is None or not isinstance(final_text, str):
            raise PersistenceHostFailed()
        return session_id, final_text

    def _event(self, line: str) -> dict[str, object]:
        # Separates wire decoding from turn-state tracking.
        try:
            event = json.loads(line)
        except ValueError as error:
            raise PersistenceHostFailed() from error
        if not isinstance(event, dict):
            raise PersistenceHostFailed()
        return event

    def _session_id(self, value: object, previous: str | None) -> str:
        # Rejects missing, malformed or unexpectedly switched sessions before any resume.
        try:
            if not isinstance(value, str):
                raise ValueError("Session ID must be a string.")
            parsed = str(UUID(value))
        except ValueError as error:
            raise PersistenceHostFailed() from error
        if previous is not None and parsed != previous:
            raise PersistenceHostFailed()
        return parsed
