"""The versioned envelope every machine-readable record travels in.

`schema_version` and `kind` are the compatibility contract: a consumer branches on them and
finds its own keys under `data`. Fields may be added, never removed or repurposed.

`CliError` is imported for typing only. A runtime import would cycle, because the errors
package imports the output manager to render failures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

if TYPE_CHECKING:
    from ..errors.cli_error import CliError


class OutputDocument(BaseModel):
    """One stable result, transition, or error record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$")
    data: dict[str, JsonValue] = Field(default_factory=dict)

    @classmethod
    def from_error(cls, error: CliError) -> OutputDocument:
        # Only explicitly safe fields cross this boundary; the private cause never does.
        # Optional fields are omitted rather than emitted as null so a shell consumer can
        # tell absent metadata from a deliberate value.
        data: dict[str, JsonValue] = {
            "code": error.code_value,
            "message": error.message,
            "description": error.description,
            "trace": error.trace,
            "file_path": error.file_path,
            "exit_code": error.exit_code,
            "retryable": error.retryable,
        }
        if error.hint is not None:
            data["hint"] = error.hint
        if error.request_id is not None:
            data["request_id"] = error.request_id
        return cls(kind="error", data=data)
