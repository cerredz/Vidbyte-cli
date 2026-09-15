"""Builds the bounded context snapshot for one suggestion run.

Only explicitly supplied files are read; nothing scans the repository or the
Codex history. File contents are treated as task data, never as instructions,
and omissions or truncations are reported in the manifest rather than hidden.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ...types.suggestions import (
    MAX_CONTEXT_CHARS,
    ContextManifestEntry,
    SuggestionContextItem,
)

ManifestStatus = Literal["included", "truncated", "omitted", "not_supplied"]

_MAX_FILE_CHARS = MAX_CONTEXT_CHARS
_MAX_TOTAL_CHARS = MAX_CONTEXT_CHARS
_SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


@dataclass(frozen=True)
class ContextSnapshot:
    """Resolved items plus the manifest and warnings the result must carry."""

    items: tuple[SuggestionContextItem, ...]
    manifest: tuple[ContextManifestEntry, ...]
    warnings: tuple[str, ...]
    by_ref: dict[str, str]


@dataclass
class _ContextAccumulator:
    """Mutable construction state kept private to one context build."""

    items: list[SuggestionContextItem] = field(default_factory=list)
    manifest: list[ContextManifestEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total: int = 0
    counter: int = 0

    def next_ref(self) -> str:
        self.counter += 1
        return f"ctx-{self.counter:03d}"


class SuggestionContextBuilder:
    """Reads explicit inputs into stable refs with hashing and limit enforcement."""

    def __init__(self) -> None:
        # No state across runs; the counter below is per-build and starts at zero.
        pass

    def build(self, fields: dict[str, tuple[str, ...]], files: tuple[Path, ...]) -> ContextSnapshot:
        # Resolves text fields first, then files, so refs stay deterministic per run.
        return self._assemble(fields, files)

    def _assemble(
        self, fields: dict[str, tuple[str, ...]], files: tuple[Path, ...]
    ) -> ContextSnapshot:
        # Keeps the orchestration small while each helper owns one input shape.
        state = _ContextAccumulator()
        self._append_fields(state, fields)
        self._append_files(state, files)
        if self._contradicts(fields):
            state.warnings.append(
                "Supplied context marks one statement both completed "
                "and in-progress; both are preserved."
            )
        return ContextSnapshot(
            items=tuple(state.items),
            manifest=tuple(state.manifest),
            warnings=tuple(state.warnings),
            by_ref={item.ref: item.content for item in state.items},
        )

    def _append_fields(
        self, state: _ContextAccumulator, fields: dict[str, tuple[str, ...]]
    ) -> None:
        # Preserves the caller's field order, which makes refs and manifests stable.
        for kind, values in fields.items():
            for value in values:
                self._append_field(state, kind, value)

    def _append_field(self, state: _ContextAccumulator, kind: str, value: str) -> None:
        # Bounds repeated flag values before Pydantic sees them.
        original = value.strip()
        if not original:
            return
        ref = state.next_ref()
        body, status, note = self._bound_text(original, f"{kind} context")
        if not self._fits(state, len(body)):
            state.manifest.append(self._manifest_entry(ref, kind, f"flag:{kind}", body, "omitted"))
            state.warnings.append(f"Omitted {kind} context: total context budget exceeded.")
            return
        state.items.append(
            SuggestionContextItem(
                ref=ref,
                kind=kind,
                label=kind,
                description="Caller-supplied context value.",
                content=body,
                source=f"flag:{kind}",
                caller_supplied=True,
            )
        )
        state.manifest.append(self._manifest_entry(ref, kind, f"flag:{kind}", body, status))
        if status == "truncated":
            state.warnings.append(note)
        state.total += len(body)

    def _append_files(self, state: _ContextAccumulator, files: tuple[Path, ...]) -> None:
        # Reads files only after all repeated flag values have been accounted for.
        for path in files:
            self._append_file(state, path)

    def _append_file(self, state: _ContextAccumulator, path: Path) -> None:
        # Rejects invalid files before adding an item or charging the total budget.
        ref = state.next_ref()
        body, status, note = self._read_one(path)
        if not body:
            state.manifest.append(self._manifest_entry(ref, "file", str(path), body, "omitted"))
            state.warnings.append(f"Omitted empty context file: {path}.")
            return
        if not self._fits(state, len(body)):
            state.manifest.append(self._manifest_entry(ref, "file", str(path), body, "omitted"))
            state.warnings.append(f"Omitted {path}: total context budget exceeded.")
            return
        state.items.append(
            SuggestionContextItem(
                ref=ref,
                kind="file",
                label=path.name,
                description="Caller-supplied file content.",
                content=body,
                source=str(path),
                caller_supplied=False,
            )
        )
        entry_status: ManifestStatus = "truncated" if status == "truncated" else "included"
        state.manifest.append(self._manifest_entry(ref, "file", str(path), body, entry_status))
        if status == "truncated":
            state.warnings.append(note)
        state.total += len(body)

    def _fits(self, state: _ContextAccumulator, chars: int) -> bool:
        # Keeps the aggregate body budget independent from prompt and metadata text.
        return state.total + chars <= _MAX_TOTAL_CHARS

    def _manifest_entry(
        self,
        ref: str,
        kind: str,
        source: str,
        body: str,
        status: ManifestStatus,
    ) -> ContextManifestEntry:
        # Hashes the exact bounded body that the agent will receive.
        return ContextManifestEntry(
            ref=ref,
            kind=kind,
            source=source,
            chars=len(body),
            sha256=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            status=status,
        )

    def _bound_text(self, text: str, label: str) -> tuple[str, ManifestStatus, str]:
        # Applies the same generous per-item cap to repeated flag values as to files.
        if len(text) <= _MAX_FILE_CHARS:
            return text, "included", ""
        kept = text[:_MAX_FILE_CHARS]
        return kept, "truncated", f"Truncated {label} to {_MAX_FILE_CHARS} chars."

    def _read_one(self, path: Path) -> tuple[str, ManifestStatus, str]:
        # Rejects directories, missing paths, and non-text shapes before reading.
        if path.is_dir():
            raise ValueError(f"context path is a directory: {path}")
        if not path.exists():
            raise ValueError(f"context file not found: {path}")
        if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported context file type: {path}")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ValueError(f"unreadable context file: {path}") from error
        if path.suffix.lower() == ".json":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"malformed JSON context file: {path}") from error
            if (
                isinstance(parsed, dict)
                and "schema_version" in parsed
                and parsed["schema_version"] != 1
            ):
                raise ValueError(f"unsupported schema version in: {path}")
            text = json.dumps(parsed, indent=2, sort_keys=True)
        if len(text) > _MAX_FILE_CHARS:
            kept = text[:_MAX_FILE_CHARS]
            return kept, "truncated", f"Truncated {path} to {_MAX_FILE_CHARS} chars."
        return text, "included", ""

    def _contradicts(self, fields: dict[str, tuple[str, ...]]) -> bool:
        # Surfaces exact-statement overlap between completed and in-progress lists.
        completed = {
            value.strip().lower() for value in fields.get("completed", ()) if value.strip()
        }
        in_progress = {
            value.strip().lower() for value in fields.get("in_progress", ()) if value.strip()
        }
        return bool(completed & in_progress)


__all__ = ["ContextSnapshot", "SuggestionContextBuilder"]
