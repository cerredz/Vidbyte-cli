"""Copies compatible `~/.vidbyte` state into the platform-native locations, and verifies it.

Two properties make this safe to run from any mutating command. It never deletes: the legacy
tree is left exactly as it was, so a user who downgrades still has working state. And it is
destination-preserving and idempotent: an existing native file always wins, so running it
twice does nothing the first run did not already do.

Every copy is read back and compared before it counts as migrated. A credential in
particular is only migrated once the keyring returns the same secret that was written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from ..auth.credentials import Credentials
from ..auth.keyring_store import KeyringCredentialStore
from ..errors.failures import LegacyCredentialUnreadable, MigrationVerificationFailed
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
        # No native file exists yet, so the expected digest is None by construction.
        self._config.save(snapshot.document, expected_digest=None)
        verified = self._config.load()
        if verified.document != snapshot.document or verified.legacy:
            raise MigrationVerificationFailed()
        return True

    def _migrate_manifests(self) -> tuple[int, int]:
        source_root = self._paths.legacy_manifests_dir()
        if not source_root.exists():
            return 0, 0
        copied = 0
        skipped = 0
        for source in source_root.rglob("*"):
            # A symlink in the legacy tree could point anywhere; copying through it would
            # pull an arbitrary file into the cache under a manifest's name.
            if source.is_symlink():
                skipped += 1
                continue
            if not source.is_file():
                continue
            destination = self._paths.manifests_dir() / source.relative_to(source_root)
            if destination.exists():
                continue
            content = source.read_bytes()
            self._writer.write(destination, content)
            if destination.read_bytes() != content:
                raise MigrationVerificationFailed()
            copied += 1
        return copied, skipped

    def _migrate_credential(self) -> bool:
        source = self._paths.legacy_credentials_file()
        if not source.exists() or not self._keyring.available():
            return False
        if self._keyring.read(DEFAULT_PROFILE, DEFAULT_API_URL) is not None:
            return False
        try:
            credentials = Credentials.model_validate(json.loads(source.read_bytes()))
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise LegacyCredentialUnreadable(error) from error
        self._keyring.write(credentials, DEFAULT_PROFILE, DEFAULT_API_URL)
        read_back = self._keyring.read(DEFAULT_PROFILE, DEFAULT_API_URL)
        if read_back is None or read_back.secret_value() != credentials.secret_value():
            raise MigrationVerificationFailed()
        return True
