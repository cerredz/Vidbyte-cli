"""FILE: src/vidbyte_cli/lib/config/paths.py

PURPOSE: Provides the single typed source of filesystem locations used by CLI state.
Native locations come from platformdirs; the historical ~/.vidbyte layout remains exposed
only for compatible reads and verified migration.

ROLE IN CODEBASE: ConfigStore, credential stores, StateMigration, manifest caching, and
operation journals receive one VidbytePaths instance instead of assembling paths ad hoc.

ARCHITECTURE NOTE: Path discovery is side-effect free. Directory creation belongs to the
specific atomic writer performing an authorized mutation.

FUNCTION INVENTORY (reviewed 2026-07-26):
- VidbytePaths.default() -> VidbytePaths: resolves native and legacy roots.
- config_file(), credentials_file(), manifests_dir(): return native state locations.
- legacy_*(): return compatibility locations under ~/.vidbyte.

WHAT NOT TO DO IN THIS FILE:
1. Do not create directories during path resolution.
2. Do not read, write, migrate, or delete state.
3. Do not put credentials in configuration or cache directories.
4. Do not restore ~/.vidbyte as the primary storage root.

TESTS: No feature tests are added under the approved no-tests workflow. Smoke invocations
isolate platformdirs through standard platform environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True)
class VidbytePaths:
    """Platform-native CLI state roots plus the read-compatible legacy root."""

    config_root: Path
    cache_root: Path
    state_root: Path
    data_root: Path
    legacy_root: Path

    @classmethod
    def default(cls) -> VidbytePaths:
        # platformdirs handles Windows, macOS, and freedesktop conventions consistently.
        directories = PlatformDirs("vidbyte-cli", "Vidbyte", roaming=False)
        return cls(
            config_root=Path(directories.user_config_path),
            cache_root=Path(directories.user_cache_path),
            state_root=Path(directories.user_state_path),
            data_root=Path(directories.user_data_path),
            legacy_root=Path.home() / ".vidbyte",
        )

    def config_file(self) -> Path:
        return self.config_root / "config.json"

    def credentials_file(self) -> Path:
        return self.data_root / "credentials.json"

    def manifests_dir(self) -> Path:
        return self.cache_root / "manifests"

    def operations_dir(self) -> Path:
        return self.state_root / "operations"

    def legacy_config_file(self) -> Path:
        return self.legacy_root / "config.json"

    def legacy_credentials_file(self) -> Path:
        return self.legacy_root / "credentials.json"

    def legacy_manifests_dir(self) -> Path:
        return self.legacy_root / "manifests"
