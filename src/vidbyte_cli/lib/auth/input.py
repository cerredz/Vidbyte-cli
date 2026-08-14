"""The two channels a login token may arrive on: a hidden prompt, or explicit stdin.

There is deliberately no `--api-key` option. An argv secret is visible in `ps`, the shell
history file, and any CI log that echoes its command line, and no amount of care at the
raise sites takes it back out of those.

Stdin is read only when `--with-token` asks for it, so a command whose input happens to be
redirected fails with a usage error instead of consuming a stream meant for something else.
The environment is absent on purpose: login persists only what a person explicitly entered.
"""

from __future__ import annotations

import getpass

from ..errors.failures import (
    ApiKeyNotLiveFormat,
    InvalidApiKeyInput,
    NoninteractiveLoginRequiresToken,
)
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
            # One past the bound, so an oversized stream is rejected rather than truncated
            # into a token that looks plausible.
            value = self._streams.stdin.read(_MAX_TOKEN_CHARACTERS + 1)
        else:
            if self._no_input or not self._terminal.interactive:
                raise NoninteractiveLoginRequiresToken()
            # The prompt goes to stderr so `login` stays usable inside a pipeline.
            value = getpass.getpass("Vidbyte API key: ", stream=self._streams.stderr)
        token = value.strip()
        if not token or len(token) > _MAX_TOKEN_CHARACTERS:
            raise InvalidApiKeyInput()
        # Bounds run first, so an accidental file redirect is reported as oversized rather
        # than prefix-tested in full.
        if not Credentials.is_live_format(token):
            raise ApiKeyNotLiveFormat()
        return Credentials.from_value(token)
