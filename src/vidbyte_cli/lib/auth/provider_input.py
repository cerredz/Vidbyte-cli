"""Acquisition of provider tokens via hidden prompt or stdin.

Mirrors CredentialInput but parameterizes by provider so prefix checks are exact.
"""

from __future__ import annotations

import getpass

from ...types.provider import Provider
from ..errors.failures import (
    InvalidProviderApiKeyInput,
    NoninteractiveProviderLoginRequiresToken,
    ProviderKeyNotLiveFormat,
)
from ..io import IOStreams
from ..io.terminal import TerminalCapabilities
from .provider_credentials import ProviderCredentials

_MAX_TOKEN_CHARACTERS = 4096


class ProviderCredentialInput:
    """Acquire one provider token through an explicit secret-safe channel."""

    def __init__(
        self,
        streams: IOStreams,
        terminal: TerminalCapabilities,
        *,
        no_input: bool,
        provider: Provider,
    ) -> None:
        # No_input and provider are fixed per command construction.
        self._streams = streams
        self._terminal = terminal
        self._no_input = no_input
        self._provider = provider

    def read(self, *, from_stdin: bool) -> ProviderCredentials:
        # Bounded read, then prefix check, so an accidental file redirect fails clearly.
        if from_stdin:
            value = self._streams.stdin.read(_MAX_TOKEN_CHARACTERS + 1)
        else:
            if self._no_input or not self._terminal.interactive:
                raise NoninteractiveProviderLoginRequiresToken(self._provider.value)
            prompt = f"{self._provider.value} API key: "
            value = getpass.getpass(prompt, stream=self._streams.stderr)
        token = value.strip()
        if not token or len(token) > _MAX_TOKEN_CHARACTERS:
            raise InvalidProviderApiKeyInput(self._provider.value)
        if not ProviderCredentials.is_live_format(self._provider, token):
            raise ProviderKeyNotLiveFormat(self._provider.value)
        return ProviderCredentials(provider=self._provider, api_key=token)  # type: ignore[arg-type]
