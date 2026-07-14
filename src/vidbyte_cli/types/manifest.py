"""The manifest contract: what commands a harness exposes and how to build them.

Resolves the types/api.ts:48 review comment. A manifest is the single source of truth the
dynamic runtime renders into click commands. Treat an incoming manifest as *data to
validate* (pydantic does that here), never as code to execute — the CLI only builds flags
and help text from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OptionType = Literal["string", "number", "boolean", "path"]


class ArgSpec(BaseModel):
    # A positional argument of a harness command.
    name: str
    required: bool = True
    description: str = ""


class OptionSpec(BaseModel):
    # A flag/option of a harness command.
    name: str
    type: OptionType = "string"
    required: bool = False
    default: object | None = None
    description: str = ""


class HarnessCommandSpec(BaseModel):
    # One subcommand of a harness (e.g. `apply`, `list`).
    name: str
    description: str
    args: list[ArgSpec] = Field(default_factory=list)
    options: list[OptionSpec] = Field(default_factory=list)
    # submit = fire and return the queued run; await = poll to completion; read = one GET.
    mode: Literal["submit", "await", "read"] = "submit"


class HarnessManifest(BaseModel):
    # The full description of a harness's command surface, served by the backend.
    name: str
    version: str
    # Fail loudly when the installed CLI is older than the manifest requires, rather than
    # silently dropping unknown flags.
    min_cli_version: str
    description: str
    commands: list[HarnessCommandSpec] = Field(default_factory=list)
