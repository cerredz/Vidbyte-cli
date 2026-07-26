"""FILE: src/vidbyte_cli/lib/config/config.py

PURPOSE: Reads and atomically writes the versioned non-secret CLI configuration document.
It preserves legacy-path compatibility while making platform-native storage authoritative.

ROLE IN CODEBASE: ConfigResolver consumes loaded documents; config get/set commands use the
typed field operations; StateMigration uses the same validation and writer boundary.

ARCHITECTURE NOTE: A write validates the current schema and compares the bytes observed by
the read-modify-write operation before replacing the file, detecting incompatible changes.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ConfigStore.load() -> ConfigSnapshot: validates native or legacy configuration.
- ConfigStore.get(field, profile) -> object: returns one allow-listed profile value.
- ConfigStore.set(field, value, profile) -> ProfileConfig: validates and persists one value.
- ConfigStore.save(document, expected_digest) -> None: atomically saves a typed document.

WHAT NOT TO DO IN THIS FILE:
1. Do not store credentials or arbitrary user-defined keys.
2. Do not repair, overwrite, or delete an invalid/future config automatically.
3. Do not return exception strings to the presentation layer.
4. Do not assemble platform paths outside VidbytePaths.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ..errors import CliError, CliErrorCode
from .atomic import AtomicFileWriter
from .models import DEFAULT_PROFILE, ConfigDocument, ConfigField, ProfileConfig
from .paths import VidbytePaths

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
        # Native state wins. Legacy state is a compatible read until migration completes.
        native = self.paths.config_file()
        if native.exists():
            return self._read(native, legacy=False)
        legacy = self.paths.legacy_config_file()
        if legacy.exists():
            return self._read(legacy, legacy=True)
        return ConfigSnapshot(ConfigDocument(), None, None)

    def get(self, field: ConfigField, profile: str = DEFAULT_PROFILE) -> object:
        snapshot = self.load()
        profile_config = self._select_profile(snapshot.document, profile)
        return getattr(profile_config, field.value)

    def set(
        self,
        field: ConfigField,
        value: str,
        profile: str = DEFAULT_PROFILE,
    ) -> ProfileConfig:
        snapshot = self.load()
        document = snapshot.document
        current = self._select_profile(document, profile)
        updated = self._updated_profile(current, field, value)
        profiles = dict(document.profiles)
        profiles[profile] = updated
        active_profile = document.active_profile if document.profiles else profile
        saved = ConfigDocument(active_profile=active_profile, profiles=profiles)
        expected_digest = self._native_digest()
        self.save(saved, expected_digest=expected_digest)
        return updated

    def save(self, document: ConfigDocument, *, expected_digest: str | None = None) -> None:
        target = self.paths.config_file()
        # @intent optimistic-config-write-conflict-detection
        # CLI state is small and writes are rare, but simultaneous shells must not silently
        # replace a schema or settings snapshot that changed after the caller read it.
        if self._native_digest() != expected_digest:
            raise CliError(
                CliErrorCode.CONFIG_WRITE_CONFLICT,
                "CLI configuration changed during this command.",
                hint="Run the command again against the latest configuration.",
                retryable=True,
            )
        encoded = document.model_dump_json(indent=2).encode("utf-8") + b"\n"
        self._writer.write(target, encoded)

    def _read(self, path: Path, *, legacy: bool) -> ConfigSnapshot:
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_CONFIG_BYTES:
                raise ValueError("configuration exceeds the size limit")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported configuration schema")
            document = ConfigDocument.model_validate(parsed)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise CliError(
                CliErrorCode.CONFIG_INVALID,
                "CLI configuration is invalid or uses an unsupported schema.",
                hint=f"Repair or move the configuration file at {path}.",
                cause=error,
            ) from error
        return ConfigSnapshot(document, path, hashlib.sha256(raw).hexdigest(), legacy)

    def _select_profile(self, document: ConfigDocument, profile: str) -> ProfileConfig:
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
        values = current.model_dump()
        values[field.value] = value
        try:
            return ProfileConfig.model_validate(values)
        except ValidationError as error:
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                f"Invalid value for configuration field '{field.value}'.",
                hint="Run 'vidbyte-cli config get' to inspect the current profile value.",
                cause=error,
            ) from error

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
            raise CliError(
                CliErrorCode.CONFIG_INVALID,
                "CLI configuration changed to an invalid or unsupported schema.",
                hint=f"Repair or move the configuration file at {path}.",
                cause=error,
            ) from error
        return hashlib.sha256(raw).hexdigest()
