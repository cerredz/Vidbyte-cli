"""FILE: src/vidbyte_cli/lib/config/migration.py

PURPOSE: Copies compatible ~/.vidbyte configuration, manifests, and credentials into their
platform-native stores, verifies every copy, and leaves the legacy source untouched.

ROLE IN CODEBASE: Mutating setup flows may invoke StateMigration before writing new state.
Read paths remain backward compatible even when migration has not run.

ARCHITECTURE NOTE: Migration is idempotent and destination-preserving: existing native
files win. Credentials are considered migrated only after keyring write and read-back.

FUNCTION INVENTORY (reviewed 2026-07-26):
- MigrationResult: immutable counts and status for one migration attempt.
- StateMigration.migrate_if_needed() -> MigrationResult: copies and verifies legacy state.

WHAT NOT TO DO IN THIS FILE:
1. Do not delete or rename legacy state.
2. Do not migrate a credential to the file fallback automatically.
3. Do not follow symlinks within the legacy manifest tree.
4. Do not expose credential values in output or exceptions.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError

from ..auth.credentials import Credentials
from ..auth.keyring_store import KeyringCredentialStore
from ..errors import CliError, CliErrorCode
from .atomic import AtomicFileWriter
from .config import ConfigStore
from .models import DEFAULT_API_URL, DEFAULT_PROFILE
from .paths import VidbytePaths


@dataclass(frozen=True)
class MigrationResult:
    """Safe migration facts that never contain copied content."""

    config_copied: bool = False
    manifests_copied: int = 0
    credential_migrated: bool = False
    skipped_symlinks: int = 0


class StateMigration:
    """Idempotently copy and verify supported legacy state."""

    def __init__(
        self,
        paths: VidbytePaths,
        config: ConfigStore,
        keyring: KeyringCredentialStore,
        writer: AtomicFileWriter | None = None,
    ) -> None:
        self._paths = paths
        self._config = config
        self._keyring = keyring
        self._writer = writer or AtomicFileWriter()

    def migrate_if_needed(self) -> MigrationResult:
        config_copied = self._migrate_config()
        manifests_copied, skipped_symlinks = self._migrate_manifests()
        credential_migrated = self._migrate_credential()
        return MigrationResult(
            config_copied=config_copied,
            manifests_copied=manifests_copied,
            credential_migrated=credential_migrated,
            skipped_symlinks=skipped_symlinks,
        )

    def _migrate_config(self) -> bool:
        if self._paths.config_file().exists() or not self._paths.legacy_config_file().exists():
            return False
        snapshot = self._config.load()
        if not snapshot.legacy:
            return False
        self._config.save(snapshot.document, expected_digest=None)
        verified = self._config.load()
        if verified.document != snapshot.document or verified.legacy:
            raise self._migration_failure()
        return True

    def _migrate_manifests(self) -> tuple[int, int]:
        source_root = self._paths.legacy_manifests_dir()
        if not source_root.exists():
            return 0, 0
        copied = 0
        skipped = 0
        for source in source_root.rglob("*"):
            if source.is_symlink():
                skipped += 1
                continue
            if not source.is_file():
                continue
            relative = source.relative_to(source_root)
            destination = self._paths.manifests_dir() / relative
            if destination.exists():
                continue
            content = source.read_bytes()
            self._writer.write(destination, content)
            if (
                hashlib.sha256(destination.read_bytes()).digest()
                != hashlib.sha256(content).digest()
            ):
                raise self._migration_failure()
            copied += 1
        return copied, skipped

    def _migrate_credential(self) -> bool:
        source = self._paths.legacy_credentials_file()
        if not source.exists() or not self._keyring.available():
            return False
        if self._keyring.read(DEFAULT_PROFILE, DEFAULT_API_URL) is not None:
            return False
        try:
            parsed = json.loads(source.read_bytes())
            credentials = Credentials.model_validate(parsed)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise CliError(
                CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                "Legacy credentials could not be migrated safely.",
                hint="Run 'vidbyte-cli login' to replace the stored credential.",
                cause=error,
            ) from error
        self._keyring.write(credentials, DEFAULT_PROFILE, DEFAULT_API_URL)
        read_back = self._keyring.read(DEFAULT_PROFILE, DEFAULT_API_URL)
        if read_back is None or read_back.secret_value() != credentials.secret_value():
            raise self._migration_failure()
        return True

    def _migration_failure(self) -> CliError:
        return CliError(
            CliErrorCode.OPERATION_FAILED,
            "Legacy CLI state could not be verified after migration.",
            hint="The legacy files were preserved; retry after checking local storage.",
        )
