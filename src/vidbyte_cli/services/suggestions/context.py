"""Builds the bounded context snapshot for one suggestion run.

Only explicitly supplied files are read; nothing scans the repository or the
Codex history. File contents are treated as task data, never as instructions,
and omissions or truncations are reported in the manifest rather than hidden.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ...types.suggestions import ContextManifestEntry, SuggestionContextItem

ManifestStatus = Literal["included", "truncated", "omitted", "not_supplied"]

_MAX_FILE_CHARS = 8000
_MAX_TOTAL_CHARS = 64000
_SUPPORTED_SUFFIXES = {".txt", ".md", ".json"}


@dataclass(frozen=True)
class ContextSnapshot:
    """Resolved items plus the manifest and warnings the result must carry."""

    items: tuple[SuggestionContextItem, ...]
    manifest: tuple[ContextManifestEntry, ...]
    warnings: tuple[str, ...]
    by_ref: dict[str, str]


class SuggestionContextBuilder:
    """Reads explicit inputs into stable refs with hashing and limit enforcement."""

    def __init__(self) -> None:
        # No state across runs; the counter below is per-build and starts at zero.
        pass

    def build(
        self, fields: dict[str, tuple[str, ...]], files: dict[str, tuple[Path, ...]]
    ) -> ContextSnapshot:
        # Resolves text fields first, then files, so refs stay deterministic per run.
        return self._assemble(fields, files)

    def _assemble(
        self, fields: dict[str, tuple[str, ...]], files: dict[str, tuple[Path, ...]]
    ) -> ContextSnapshot:
        # Assigns ctx-N refs in insertion order across fields then files.
        items: list[SuggestionContextItem] = []
        manifest: list[ContextManifestEntry] = []
        warnings: list[str] = []
        counter = 0

        def _next_ref() -> str:
            nonlocal counter
            counter += 1
            return f"ctx-{counter:03d}"

        total = 0
        for kind, values in fields.items():
            for value in values:
                ref = _next_ref()
                body = value.strip()
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
                items.append(
                    SuggestionContextItem(
                        ref=ref,
                        kind=kind,
                        label=kind,
                        content=body,
                        source=f"flag:{kind}",
                        caller_supplied=True,
                    )
                )
                manifest.append(
                    ContextManifestEntry(
                        ref=ref,
                        kind=kind,
                        source=f"flag:{kind}",
                        chars=len(body),
                        sha256=digest,
                        status="included",
                    )
                )
                total += len(body)
        for kind, paths in files.items():
            for path in paths:
                ref = _next_ref()
                try:
                    body, status, note = self._read_one(path)
                except ValueError as error:
                    raise ValueError(str(error)) from error
                if total + len(body) > _MAX_TOTAL_CHARS:
                    manifest.append(
                        ContextManifestEntry(
                            ref=ref,
                            kind=kind,
                            source=str(path),
                            chars=len(body),
                            sha256=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
                            status="omitted",
                        )
                    )
                    warnings.append(f"Omitted {path}: total context budget exceeded.")
                    continue
                total += len(body)
                if status == "truncated":
                    warnings.append(note)
                items.append(
                    SuggestionContextItem(
                        ref=ref,
                        kind=kind,
                        label=path.name,
                        content=body,
                        source=str(path),
                        caller_supplied=False,
                    )
                )
                entry_status: ManifestStatus = "truncated" if status == "truncated" else "included"
                manifest.append(
                    ContextManifestEntry(
                        ref=ref,
                        kind=kind,
                        source=str(path),
                        chars=len(body),
                        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
                        status=entry_status,
                    )
                )
        if self._contradicts(fields):
            warnings.append(
                "Supplied context marks one statement both completed "
                "and in-progress; both are preserved."
            )
        by_ref = {item.ref: item.content for item in items}
        return ContextSnapshot(
            items=tuple(items), manifest=tuple(manifest), warnings=tuple(warnings), by_ref=by_ref
        )

    def _read_one(self, path: Path) -> tuple[str, str, str]:
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
            value.strip().lower() for value in fields.get("in-progress", ()) if value.strip()
        }
        return bool(completed & in_progress)
