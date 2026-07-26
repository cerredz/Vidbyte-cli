"""FILE: src/vidbyte_cli/lib/harness/catalog.py

PURPOSE: Loads validated harness manifests cache-first, quarantines corrupt entries,
refreshes from one typed endpoint, and enforces minimum CLI version.

ROLE IN CODEBASE: HarnessRegistry uses this boundary during the second command-tree pass.
Only the requested namespace is loaded.

ARCHITECTURE NOTE: Backend manifests remain data. Cache filenames are allow-listed and
writes use the shared atomic state primitive.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ...types.manifest import HarnessManifest
from ..config.atomic import AtomicFileWriter
from ..errors import CliError, CliErrorCode
from ..runtime.version import current_version
from .context import HarnessContext

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class HarnessCatalog:
    """Cache-first manifest source for one invocation."""

    def __init__(self, ctx: HarnessContext) -> None:
        self._ctx = ctx
        self._writer = AtomicFileWriter()

    def load(self, name: str) -> HarnessManifest:
        path = self._path(name)
        if path.exists():
            try:
                manifest = HarnessManifest.model_validate_json(path.read_bytes())
                self._check_version(manifest)
                return manifest
            except (OSError, ValidationError, ValueError):
                self._quarantine(path)
        return self.refresh(name)

    def refresh(self, name: str) -> HarnessManifest:
        manifest = self._ctx.harness_endpoints().get_manifest(name)
        if manifest.name != name:
            raise self._protocol_error()
        self._check_version(manifest)
        self._writer.write(
            self._path(name),
            manifest.model_dump_json(indent=2).encode("utf-8") + b"\n",
        )
        return manifest

    def _path(self, name: str) -> Path:
        if not _SAFE_NAME.fullmatch(name):
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                "The harness namespace is invalid.",
                2,
            )
        return Path(self._ctx.manifest_cache_dir()) / f"{name}.json"

    def _quarantine(self, path: Path) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        destination = path.with_name(f"{path.name}.corrupt.{timestamp}")
        try:
            path.replace(destination)
        except OSError as error:
            raise CliError(
                CliErrorCode.OPERATION_FAILED,
                "A corrupt harness manifest cache could not be quarantined.",
                hint="Remove the affected manifest cache file and retry.",
                cause=error,
            ) from error

    def _check_version(self, manifest: HarnessManifest) -> None:
        if self._version_tuple(current_version()) < self._version_tuple(manifest.min_cli_version):
            raise CliError(
                CliErrorCode.OPERATION_FAILED,
                f"Harness '{manifest.name}' requires a newer Vidbyte CLI.",
                hint=f"Upgrade to version {manifest.min_cli_version} or newer.",
            )

    def _version_tuple(self, value: str) -> tuple[int, int, int]:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", value)
        if match is None:
            raise self._protocol_error()
        major, minor, patch = match.groups()
        return int(major), int(minor), int(patch)

    def _protocol_error(self) -> CliError:
        return CliError(
            CliErrorCode.API_PROTOCOL_ERROR,
            "The harness manifest is incompatible with this CLI.",
            hint="Refresh the manifest or upgrade the CLI.",
        )
