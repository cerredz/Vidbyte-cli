"""Discovery and bounded execution for provider-owned native CLIs.

Only GitHub has a native path today (gh). Slack and Drive stay direct-only.
Vidbyte keyring tokens never enter native argv, env, or errors.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

_MAX_STDOUT_BYTES = 1_048_576
_PROBE_TIMEOUT_SECONDS = 10.0
_EXCERPT_CHARS = 500


@dataclass(frozen=True)
class NativeAvailability:
    """Cached result of one native CLI probe."""

    found: bool
    authenticated: bool
    version: str | None = None


@dataclass(frozen=True)
class NativeResult:
    """Parsed JSON from one allowlisted native invocation."""

    payload: dict[str, object]
    argv: tuple[str, ...]


class NativeProbe:
    """Discovers the gh binary without ever failing the caller."""

    def __init__(self) -> None:
        # Cache per manager instance so status and read share one probe.
        self._cached: NativeAvailability | None = None

    def github(self) -> NativeAvailability:
        # Returns cached availability or probes PATH plus auth status once.
        if self._cached is not None:
            return self._cached
        self._cached = self._probe_gh()
        return self._cached

    def reset(self) -> None:
        # Clears the cache so tests can simulate install and uninstall.
        self._cached = None

    def _probe_gh(self) -> NativeAvailability:
        # Missing or non-executable binaries record missing instead of raising.
        if shutil.which("gh") is None:
            return NativeAvailability(found=False, authenticated=False)
        try:
            versioned = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                timeout=_PROBE_TIMEOUT_SECONDS,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return NativeAvailability(found=False, authenticated=False)
        if versioned.returncode != 0:
            return NativeAvailability(found=False, authenticated=False)
        try:
            authed = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=_PROBE_TIMEOUT_SECONDS,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return NativeAvailability(
                found=True, authenticated=False, version=self._parse_version(versioned.stdout)
            )
        return NativeAvailability(
            found=True,
            authenticated=authed.returncode == 0,
            version=self._parse_version(versioned.stdout),
        )

    def _parse_version(self, text: str) -> str | None:
        # Parses gh version X.Y.Z best-effort and keeps None when unrecognized.
        match = re.search(r"gh version (\d+\.\d+\.\d+)", text)
        return match.group(1) if match else None


class NativeRunner:
    """Runs one allowlisted argv with timeout, size cap, and strict JSON parsing."""

    def __init__(self, timeout_seconds: float) -> None:
        # Timeout comes from the invocation so reads respect --request-timeout.
        self._timeout = max(1.0, timeout_seconds)

    def run(self, argv: tuple[str, ...]) -> NativeResult:
        # Spawns without a shell and returns validated JSON object payloads only.
        from ..errors.failures import (
            ConnectionApiUnavailable,
            ConnectionNativeCliMissing,
            ConnectionProtocolError,
        )

        if not argv or argv[0] != "gh":
            raise ConnectionNativeCliMissing("gh")
        if shutil.which("gh") is None:
            raise ConnectionNativeCliMissing("gh")
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ConnectionApiUnavailable("github", error) from error
        except OSError as error:
            raise ConnectionNativeCliMissing("gh") from error
        if completed.returncode != 0:
            raise self._classify_failure(completed.stderr or completed.stdout)
        raw = completed.stdout.encode("utf-8", errors="replace")
        if len(raw) > _MAX_STDOUT_BYTES:
            raise ConnectionProtocolError("github", ValueError("native output oversized"))
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ConnectionProtocolError("github", error) from error
        if not isinstance(payload, dict):
            raise ConnectionProtocolError("github", ValueError("native result shape"))
        return NativeResult(payload=payload, argv=argv)

    def _classify_failure(self, output: str) -> Exception:
        # Maps provider wording to the existing typed failure vocabulary.
        from ..errors.failures import (
            ConnectionAuthenticationRequired,
            ConnectionNativeCliFailed,
            ConnectionRateLimited,
            ConnectionResourceUnavailable,
        )

        lowered = output.lower()
        if "not authenticated" in lowered or "auth status" in lowered or "not logged" in lowered:
            return ConnectionAuthenticationRequired("github")
        if (
            "could not resolve to a repository" in lowered
            or "not found" in lowered
            or "no pull request" in lowered
        ):
            return ConnectionResourceUnavailable("github")
        if "rate limit" in lowered or ("exceeded" in lowered and "limit" in lowered):
            return ConnectionRateLimited("github")
        return ConnectionNativeCliFailed("gh", self._excerpt(output))

    def _excerpt(self, output: str) -> str:
        # Strips control chars and bounds the excerpt so logs cannot grow output.
        cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", output).strip()
        collapsed = re.sub(r"\s+", " ", cleaned)
        return collapsed[:_EXCERPT_CHARS]
