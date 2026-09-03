"""PATH-only discovery for supported native coding-agent executables.

Discovery never invokes a host, reads its configuration, or inspects environment values.
An explicit unavailable host is never silently replaced with a different agent.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable

from ...types.runtime import RuntimeHost, RuntimeHostStatus
from ..errors.failures import RuntimeHostUnavailable

_HOST_ORDER = (RuntimeHost.CODEX, RuntimeHost.CLAUDE, RuntimeHost.OPENCODE)


class RuntimeHostRegistry:
    """Discovers and selects the user's installed native coding-agent hosts."""

    def __init__(self, which: Callable[[str], str | None] = shutil.which) -> None:
        # Makes PATH resolution injectable while using the operating system by default.
        self._which = which

    def inspect(self) -> tuple[RuntimeHostStatus, ...]:
        # Returns stable host order so human and machine output remain predictable.
        return tuple(self._status(host) for host in _HOST_ORDER)

    def resolve(self, requested: RuntimeHost | None) -> RuntimeHostStatus:
        # Honors explicit selection; auto mode chooses the first available reviewed host.
        statuses = self.inspect()
        if requested is not None:
            selected = next(status for status in statuses if status.host is requested)
            if not selected.available:
                raise RuntimeHostUnavailable(requested.value)
            return selected
        automatic = next((status for status in statuses if status.available), None)
        if automatic is None:
            raise RuntimeHostUnavailable("codex, claude, or opencode")
        return automatic

    def _status(self, host: RuntimeHost) -> RuntimeHostStatus:
        # Records only the resolved executable path, never host configuration or credentials.
        executable = self._which(host.value)
        return RuntimeHostStatus(host=host, available=executable is not None, executable=executable)
