"""FILE: src/vidbyte_cli/lib/output/models.py

PURPOSE: Defines the versioned JSON documents emitted on machine-readable channels.
Feature presenters supply stable kinds and JSON-compatible data; stream selection and human
formatting remain OutputManager responsibilities.

ROLE IN CODEBASE: OutputManager accepts OutputDocument for results and transitions.
error_document() converts CliError metadata into the same versioned envelope so automation
always receives schema_version and kind.

ARCHITECTURE NOTE: A small envelope stabilizes cross-command parsing while feature-specific
data remains owned by its presenter. Pydantic rejects non-JSON values before serialization.

FUNCTION INVENTORY (reviewed 2026-07-26):
- SafeError: display-safe protocol accepted without importing the error package.
- OutputDocument: schema-versioned machine result or transition envelope.
- error_document(error) -> OutputDocument: creates a safe structured error envelope.

COMMON MODIFICATION PATTERNS: Add fields only compatibly, keep schema_version literal, and
let a feature own the documented keys within its data object.

WHAT NOT TO DO IN THIS FILE:
1. Do not place human prose layout or terminal escape sequences in documents.
2. Do not serialize Exception objects, causes, credentials, prompts, or response bodies.
3. Do not infer a feature kind from class names.
4. Do not remove schema_version or kind.

KNOWN EDGE CASES: Optional error fields are omitted rather than serialized as null so shell
consumers can distinguish absent metadata from an explicit value.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines the versioned machine-output contract.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py validates emitted JSON documents through public invocations.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class SafeError(Protocol):
    """Display-safe fields accepted by error_document without package coupling."""

    @property
    def code_value(self) -> str: ...

    message: str
    exit_code: int
    hint: str | None
    retryable: bool
    request_id: str | None


class OutputDocument(BaseModel):
    """One stable result, transition, or error record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$")
    data: dict[str, JsonValue] = Field(default_factory=dict)


def error_document(error: SafeError) -> OutputDocument:
    # The cause is intentionally absent: only explicitly safe fields cross this boundary.
    data: dict[str, JsonValue] = {
        "code": error.code_value,
        "message": error.message,
        "exit_code": error.exit_code,
        "retryable": error.retryable,
    }
    if error.hint is not None:
        data["hint"] = error.hint
    if error.request_id is not None:
        data["request_id"] = error.request_id
    return OutputDocument(kind="error", data=data)
