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
from .config import ConfigStore
from .models import DEFAULT_API_URL, DEFAULT_PROFILE
from .paths import VidbytePaths


@dataclass(frozen=True)
class MigrationResult:
    """Safe migration facts that never contain copied content."""

    config_copied: bool = False
    credential_migrated: bool = False


class StateMigration:
    """Idempotently copy and verify supported legacy state."""

    def __init__(
        self,
        paths: VidbytePaths,
        config: ConfigStore,
        keyring: KeyringCredentialStore,
    ) -> None:
        self._paths = paths
        self._config = config
        self._keyring = keyring

    def migrate_if_needed(self) -> MigrationResult:
        return MigrationResult(
            config_copied=self._migrate_config(),
            credential_migrated=self._migrate_credential(),
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
