"""Reads user-typed prompts from the transcripts coding-agent hosts already save on disk.

Each host keeps its own undocumented format, so each gets one small reader that knows only where
its files live and which records are prompts a person typed. Readers never raise on a malformed
file or line: an unreadable record is skipped, because one corrupt session must not block a scan
of hundreds. `TranscriptLibrary` applies the caller's scope (hosts, dates, project, and counts)
on top of every reader, newest sessions first.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from ...types.rules import RulesHost, RulesScanScope

_MILLISECONDS_THRESHOLD = 10**11


@dataclass(frozen=True)
class TranscriptPrompt:
    """One prompt a person typed, with a prompt ID that stays stable across re-reads."""

    host: RulesHost
    session_id: str
    prompt_id: str
    text: str
    project: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class TranscriptSession:
    """One saved session and the prompts a person typed into it, oldest first."""

    host: RulesHost
    session_id: str
    path: Path
    project: str | None
    started_at: datetime | None
    prompts: tuple[TranscriptPrompt, ...]

    @property
    def latest_at(self) -> datetime | None:
        # The newest prompt time, falling back to the session start.
        times = [prompt.created_at for prompt in self.prompts if prompt.created_at is not None]
        return max(times) if times else self.started_at


class TranscriptTime:
    """Parses the timestamp shapes the hosts write: ISO strings and epoch milliseconds."""

    @staticmethod
    def parse(value: object) -> datetime | None:
        # Returns an aware UTC datetime, or None for anything unrecognizable.
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > _MILLISECONDS_THRESHOLD else value
            try:
                return datetime.fromtimestamp(seconds, tz=UTC)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str) and value.strip():
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return None

    @staticmethod
    def modified(path: Path) -> datetime | None:
        # A file's modification time, used to skip files older than the scan window cheaply.
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return None


class TranscriptText:
    """Extracts prompt text from the string-or-block content shapes the hosts share."""

    @staticmethod
    def of(content: object, text_types: tuple[str, ...] = ("text", "input_text")) -> str:
        # Joins text blocks and ignores tool results, images, and other non-text blocks.
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") in text_types
        ]
        return "\n".join(part for part in parts if part.strip()).strip()


class JsonLines:
    """Yields each decodable JSON object in a JSON Lines file, skipping everything else."""

    @staticmethod
    def read(path: Path, marker: str | None = None) -> Iterator[dict[str, Any]]:
        # A cheap substring marker skips most lines before paying for json.loads.
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if marker is not None and marker not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict):
                        yield record
        except OSError:
            return

    @staticmethod
    def mapping(value: object) -> dict[str, Any]:
        # Narrows a nested JSON value to a mapping, treating anything else as empty.
        return value if isinstance(value, dict) else {}

    @staticmethod
    def document(path: Path) -> dict[str, Any]:
        # Reads one JSON document, returning an empty mapping when it is unreadable.
        try:
            record = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return {}
        return record if isinstance(record, dict) else {}


class TranscriptSource:
    """One host's transcript folder and how to read prompts out of it."""

    host: RulesHost

    def __init__(self, home: Path) -> None:
        # The home directory is injected so tests and profiles never touch the real one.
        self._home = home

    def root(self) -> Path:
        # The folder this host writes its session transcripts into.
        raise NotImplementedError

    def session_files(self) -> list[Path]:
        # Every candidate session file or folder under the root.
        raise NotImplementedError

    def read_session(self, path: Path) -> TranscriptSession | None:
        # Parses one session, or returns None when it holds no user-typed prompt.
        raise NotImplementedError

    def read_sessions(self, since: datetime | None) -> list[TranscriptSession]:
        # Reads every session touched since `since`, skipping older files without parsing them.
        sessions: list[TranscriptSession] = []
        for path in self.session_files():
            modified = TranscriptTime.modified(path)
            if since is not None and modified is not None and modified < since:
                continue
            session = self.read_session(path)
            if session is not None and session.prompts:
                sessions.append(session)
        return sessions

    def _prompts(
        self, session_id: str, project: str | None, items: list[tuple[str, datetime | None]]
    ) -> tuple[TranscriptPrompt, ...]:
        # Numbers each prompt by its position in the session, which keeps IDs stable on re-read.
        return tuple(
            TranscriptPrompt(
                self.host,
                session_id,
                f"{self.host.value}:{session_id}:{ordinal}",
                text,
                project,
                created_at,
            )
            for ordinal, (text, created_at) in enumerate(items)
            if text
        )


class ClaudeTranscripts(TranscriptSource):
    """Claude Code: ~/.claude/projects/<project-slug>/<session>.jsonl."""

    host = RulesHost.CLAUDE

    def root(self) -> Path:
        # Claude Code keeps one folder per project under ~/.claude/projects.
        return self._home / ".claude" / "projects"

    def session_files(self) -> list[Path]:
        # Only top-level session files; subagent transcripts live in nested folders.
        return sorted(self.root().glob("*/*.jsonl")) if self.root().is_dir() else []

    def read_session(self, path: Path) -> TranscriptSession | None:
        # Keeps main-thread user turns and drops tool results, meta records, and subagent turns.
        items: list[tuple[str, datetime | None]] = []
        session_id, project = path.stem, None
        for record in JsonLines.read(path, marker='"user"'):
            if record.get("type") != "user" or record.get("isSidechain") or record.get("isMeta"):
                continue
            message = record.get("message")
            text = TranscriptText.of(
                message.get("content") if isinstance(message, dict) else None, ("text",)
            )
            session_id = str(record.get("sessionId") or session_id)
            project = project or (str(record["cwd"]) if record.get("cwd") else None)
            items.append((text, TranscriptTime.parse(record.get("timestamp"))))
        prompts = self._prompts(session_id, project, items)
        started = next((prompt.created_at for prompt in prompts if prompt.created_at), None)
        return TranscriptSession(self.host, session_id, path, project, started, prompts)


class CodexTranscripts(TranscriptSource):
    """Codex: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl."""

    host = RulesHost.CODEX

    def root(self) -> Path:
        # Codex writes one rollout file per session under dated folders.
        return self._home / ".codex" / "sessions"

    def session_files(self) -> list[Path]:
        # Every rollout file at any depth under the dated folders.
        return sorted(self.root().rglob("rollout-*.jsonl")) if self.root().is_dir() else []

    def read_session(self, path: Path) -> TranscriptSession | None:
        # Prefers explicit user_message events, falling back to user-role input items.
        events: list[tuple[str, datetime | None]] = []
        inputs: list[tuple[str, datetime | None]] = []
        session_id, project, started = path.stem, None, None
        for record in JsonLines.read(path):
            payload = JsonLines.mapping(record.get("payload"))
            when = TranscriptTime.parse(record.get("timestamp"))
            if record.get("type") == "session_meta":
                session_id = str(payload.get("id") or session_id)
                project = str(payload["cwd"]) if payload.get("cwd") else None
                started = TranscriptTime.parse(payload.get("timestamp")) or when
            elif record.get("type") == "event_msg" and payload.get("type") == "user_message":
                events.append((str(payload.get("message") or "").strip(), when))
            elif (
                record.get("type") == "response_item"
                and payload.get("type") == "message"
                and payload.get("role") == "user"
            ):
                inputs.append((TranscriptText.of(payload.get("content")), when))
        prompts = self._prompts(session_id, project, events or inputs)
        return TranscriptSession(self.host, session_id, path, project, started, prompts)


class GrokTranscripts(TranscriptSource):
    """Grok Build: ~/.grok/sessions/<encoded-cwd>/<session-id>/chat_history.jsonl."""

    host = RulesHost.GROK

    def root(self) -> Path:
        # GROK_HOME overrides ~/.grok, exactly as Grok Build resolves it.
        grok_home = os.environ.get("GROK_HOME")
        return (Path(grok_home) if grok_home else self._home / ".grok") / "sessions"

    def session_files(self) -> list[Path]:
        # Each session is a folder holding chat_history.jsonl and summary.json.
        return sorted(self.root().glob("*/*/chat_history.jsonl")) if self.root().is_dir() else []

    def read_session(self, path: Path) -> TranscriptSession | None:
        # Keeps typed user messages and drops the ones Grok marks as synthetic.
        folder = path.parent
        summary = JsonLines.document(folder / "summary.json")
        started = TranscriptTime.parse(summary.get("created_at"))
        project = self._project(folder.parent)
        items = [
            (TranscriptText.of(record.get("content"), ("text",)), started)
            for record in JsonLines.read(path, marker='"user"')
            if record.get("type") == "user" and not record.get("synthetic_reason")
        ]
        prompts = self._prompts(folder.name, project, items)
        return TranscriptSession(self.host, folder.name, path, project, started, prompts)

    @staticmethod
    def _project(group: Path) -> str | None:
        # Grok URL-encodes the working directory, or stores long ones in a .cwd file.
        cwd_file = group / ".cwd"
        if cwd_file.is_file():
            try:
                return cwd_file.read_text(encoding="utf-8").strip() or None
            except OSError:
                return None
        return unquote(group.name) or None


class OpenCodeTranscripts(TranscriptSource):
    """OpenCode: storage/{session,message,part} JSON documents under the XDG data home."""

    host = RulesHost.OPENCODE

    def root(self) -> Path:
        # XDG_DATA_HOME overrides ~/.local/share on every platform OpenCode supports.
        data_home = os.environ.get("XDG_DATA_HOME")
        return (
            (Path(data_home) if data_home else self._home / ".local" / "share")
            / "opencode"
            / "storage"
        )

    def session_files(self) -> list[Path]:
        # One session document per session, grouped by project.
        folder = self.root() / "session"
        return sorted(folder.glob("*/*.json")) if folder.is_dir() else []

    def read_sessions(self, since: datetime | None) -> list[TranscriptSession]:
        # Session documents are not rewritten per message, so the message folder's time is used.
        sessions: list[TranscriptSession] = []
        for path in self.session_files():
            messages = self.root() / "message" / path.stem
            modified = TranscriptTime.modified(messages) or TranscriptTime.modified(path)
            if since is not None and modified is not None and modified < since:
                continue
            session = self.read_session(path)
            if session is not None and session.prompts:
                sessions.append(session)
        return sessions

    def read_session(self, path: Path) -> TranscriptSession | None:
        # Joins each user message's text parts, oldest message first.
        meta = JsonLines.document(path)
        session_id = str(meta.get("id") or path.stem)
        times = JsonLines.mapping(meta.get("time"))
        started = TranscriptTime.parse(times.get("created"))
        project = str(meta["directory"]) if meta.get("directory") else None
        messages = [
            JsonLines.document(item)
            for item in sorted((self.root() / "message" / session_id).glob("*.json"))
        ]
        users = sorted(
            (message for message in messages if message.get("role") == "user"), key=self._created
        )
        items = [
            (
                self._text(str(message.get("id") or "")),
                TranscriptTime.parse(self._created(message) or None),
            )
            for message in users
        ]
        return TranscriptSession(
            self.host, session_id, path, project, started, self._prompts(session_id, project, items)
        )

    @staticmethod
    def _created(message: dict[str, Any]) -> float:
        # Message creation time in epoch milliseconds, zero when absent.
        times = JsonLines.mapping(message.get("time"))
        value = times.get("created")
        return (
            float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
        )

    def _text(self, message_id: str) -> str:
        # Concatenates a message's typed text parts in part-ID order, skipping synthetic parts.
        if not message_id:
            return ""
        parts = [
            JsonLines.document(item)
            for item in sorted((self.root() / "part" / message_id).glob("*.json"))
        ]
        texts = [
            str(part.get("text") or "")
            for part in parts
            if part.get("type") == "text" and not part.get("synthetic")
        ]
        return "\n".join(text for text in texts if text.strip()).strip()


class TranscriptLibrary:
    """Every supported host's transcripts, filtered by one scan scope."""

    def __init__(self, home: Path | None = None) -> None:
        # Builds one reader per host over the same home directory.
        base = home or Path.home()
        self._sources = {
            source.host: source
            for source in (
                ClaudeTranscripts(base),
                CodexTranscripts(base),
                GrokTranscripts(base),
                OpenCodeTranscripts(base),
            )
        }

    def hosts(self) -> tuple[TranscriptSource, ...]:
        # Every reader in a stable order, whether or not its folder exists.
        return tuple(self._sources.values())

    def source(self, host: RulesHost) -> TranscriptSource:
        # The reader for one host.
        return self._sources[host]

    def sessions(self, scope: RulesScanScope) -> list[TranscriptSession]:
        # In-scope sessions trimmed to in-window prompts, newest first, capped by max_sessions.
        selected: list[TranscriptSession] = []
        for host in scope.hosts:
            for session in self._sources[host].read_sessions(scope.since):
                trimmed = self._within_scope(session, scope)
                if trimmed is not None:
                    selected.append(trimmed)
        selected.sort(
            key=lambda item: item.latest_at or datetime.min.replace(tzinfo=UTC), reverse=True
        )
        return selected[: scope.max_sessions] if scope.max_sessions is not None else selected

    def prompts(self, scope: RulesScanScope) -> list[TranscriptPrompt]:
        # Prompts of the selected sessions, newest session first, capped by max_prompts.
        prompts = [prompt for session in self.sessions(scope) for prompt in session.prompts]
        return prompts[: scope.max_prompts] if scope.max_prompts is not None else prompts

    def _within_scope(
        self, session: TranscriptSession, scope: RulesScanScope
    ) -> TranscriptSession | None:
        # Keeps only prompts inside the time window, and drops sessions outside the project.
        if scope.project is not None and not self._same_project(session.project, scope.project):
            return None
        kept = tuple(
            prompt
            for prompt in session.prompts
            if self._in_window(prompt.created_at or session.started_at, scope)
        )
        return replace(session, prompts=kept) if kept else None

    @staticmethod
    def _in_window(moment: datetime | None, scope: RulesScanScope) -> bool:
        # A prompt with no known time is kept; the file-time pre-filter already bounded it.
        if moment is None:
            return True
        if scope.since is not None and moment < scope.since:
            return False
        return not (scope.until is not None and moment > scope.until)

    @staticmethod
    def _same_project(project: str | None, wanted: str) -> bool:
        # Path-prefix match that ignores case and slash direction, as Windows paths require.
        if not project:
            return False
        have, want = (
            TranscriptLibrary._normalize_path(project),
            TranscriptLibrary._normalize_path(wanted),
        )
        return have == want or have.startswith(want + "/")

    @staticmethod
    def _normalize_path(value: str) -> str:
        # Forward slashes, no trailing slash, case-folded.
        return value.replace("\\", "/").rstrip("/").casefold()
