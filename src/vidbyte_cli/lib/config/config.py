"""Reads and atomically writes the versioned non-secret CLI configuration document.

Native state wins over legacy state, and neither is ever repaired in place: a document the
CLI cannot validate is reported, not overwritten, because a parse failure is far more often
a bug or a partial write than a file the user wanted destroyed.

Writes are read-modify-write, so `save` compares a digest of the file it is about to replace
against the one the caller read. Two shells running `config set` at once is rare, but the
losing write would silently discard the other's setting, and the check costs one read.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ..errors.failures import (
    ConfigInvalidBeforeWrite,
    ConfigUnreadable,
    ConfigWriteConflict,
    InvalidConfigValue,
)
from .atomic import AtomicFileWriter
from .models import DEFAULT_PROFILE, ConfigDocument, ConfigField, ProfileConfig
from .paths import VidbytePaths

# Configuration is a handful of scalars; anything this large is a wrong or hostile file, and
# the bound keeps it from being read into memory before validation can reject it.
_MAX_CONFIG_BYTES = 1_000_000


@dataclass(frozen=True)
class ConfigSnapshot:
    """One validated document plus concurrency and provenance metadata."""

    document: ConfigDocument
    path: Path | None
    digest: str | None
    legacy: bool = False


class ConfigStore:
    """Typed local store for non-secret profile configuration."""

    def __init__(
        self,
        paths: VidbytePaths | None = None,
        writer: AtomicFileWriter | None = None,
    ) -> None:
        self.paths = paths or VidbytePaths.default()
        self._writer = writer or AtomicFileWriter()

    def load(self) -> ConfigSnapshot:
        # Native state wins. Legacy state stays a compatible read until migration runs, so a
        # user who never logs in again keeps their settings.
        native = self.paths.config_file()
        if native.exists():
            return self._read(native, legacy=False)
        legacy = self.paths.legacy_config_file()
        if legacy.exists():
            return self._read(legacy, legacy=True)
        return ConfigSnapshot(ConfigDocument(), None, None)

    def get(self, field: ConfigField, profile: str = DEFAULT_PROFILE) -> object:
        snapshot = self.load()
        return getattr(self._select_profile(snapshot.document, profile), field.value)

    def set(self, field: ConfigField, value: str, profile: str = DEFAULT_PROFILE) -> ProfileConfig:
        snapshot = self.load()
        document = snapshot.document
        updated = self._updated_profile(self._select_profile(document, profile), field, value)
        profiles = dict(document.profiles)
        profiles[profile] = updated
        active_profile = document.active_profile if document.profiles else profile
        saved = ConfigDocument(active_profile=active_profile, profiles=profiles)
        # The digest of the native file, not the snapshot's: a legacy read has no native
        # file yet, and this write is what creates it.
        self.save(saved, expected_digest=self._native_digest())
        return updated

    def save(self, document: ConfigDocument, *, expected_digest: str | None = None) -> None:
        if self._native_digest() != expected_digest:
            raise ConfigWriteConflict()
        encoded = document.model_dump_json(indent=2).encode("utf-8") + b"\n"
        self._writer.write(self.paths.config_file(), encoded)

    def _read(self, path: Path, *, legacy: bool) -> ConfigSnapshot:
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_CONFIG_BYTES:
                raise ValueError("configuration exceeds the size limit")
            parsed = json.loads(raw)
            # Checked before validation so a future document reports its version rather than
            # a list of fields this release happens not to know.
            if isinstance(parsed, dict) and parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported configuration schema")
            document = ConfigDocument.model_validate(parsed)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise ConfigUnreadable(str(path), error) from error
        return ConfigSnapshot(document, path, hashlib.sha256(raw).hexdigest(), legacy)

    def _select_profile(self, document: ConfigDocument, profile: str) -> ProfileConfig:
        # An unknown profile falls back rather than failing: a profile may exist only as a
        # credential scope, with no stored settings of its own.
        selected = document.profiles.get(profile)
        if selected is not None:
            return selected
        return document.profiles.get(DEFAULT_PROFILE, ProfileConfig())

    def _updated_profile(
        self,
        current: ProfileConfig,
        field: ConfigField,
        value: str,
    ) -> ProfileConfig:
        # Revalidating the whole profile keeps one validation path for command, environment,
        # and persisted values, so `config set` cannot write what `load` would reject.
        values = current.model_dump()
        values[field.value] = value
        try:
            return ProfileConfig.model_validate(values)
        except ValidationError as error:
            raise InvalidConfigValue(field.value, error) from error

    def _native_digest(self) -> str | None:
        path = self.paths.config_file()
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported configuration schema")
            ConfigDocument.model_validate(parsed)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise ConfigInvalidBeforeWrite(str(path), error) from error
        return hashlib.sha256(raw).hexdigest()
