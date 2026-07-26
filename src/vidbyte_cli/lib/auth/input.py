"""FILE: src/vidbyte_cli/lib/auth/input.py

PURPOSE: Reads login tokens without accepting raw secret argv values. Explicit stdin is
bounded; interactive entry uses a hidden terminal prompt and respects --no-input.

ROLE IN CODEBASE: LoginCommand delegates token acquisition here before verification.

ARCHITECTURE NOTE: Environment tokens are intentionally absent because login persists only
an explicitly entered value. CredentialResolver may still use the environment transiently.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CredentialInput.read(from_stdin) -> Credentials: returns bounded explicit input.

WHAT NOT TO DO IN THIS FILE:
1. Do not echo or log token input.
2. Do not accept a token as a command-line option value.
3. Do not read redirected stdin unless --with-token explicitly requests it.
4. Do not persist or verify the token.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import getpass

from ..errors import usage_error
from ..io import IOStreams
from ..io.terminal import TerminalCapabilities
from .credentials import Credentials

_MAX_TOKEN_CHARACTERS = 4096


class CredentialInput:
    """Acquire one token through an explicit secret-safe channel."""

    def __init__(
        self,
        streams: IOStreams,
        terminal: TerminalCapabilities,
        *,
        no_input: bool,
    ) -> None:
        self._streams = streams
        self._terminal = terminal
        self._no_input = no_input

    def read(self, *, from_stdin: bool) -> Credentials:
        if from_stdin:
            value = self._streams.stdin.read(_MAX_TOKEN_CHARACTERS + 1)
        else:
            if self._no_input or not self._terminal.interactive:
                raise usage_error(
                    "Login requires explicit token input in noninteractive mode.",
                    "Pipe the token to 'vidbyte-cli login --with-token'.",
                )
            value = getpass.getpass("Vidbyte API key: ", stream=self._streams.stderr)
        token = value.strip()
        if not token or len(token) > _MAX_TOKEN_CHARACTERS:
            raise usage_error("The supplied Vidbyte API key is empty or too large.")
        return Credentials.from_value(token)
