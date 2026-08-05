"""Single source of truth for every path the CLI reads or writes.

Native locations come from platformdirs so config, cache, state, and data land where each
platform expects them. The historical `~/.vidbyte` tree stays exposed, but only for
compatible reads and verified migration — it is never the primary root again.

Resolution is side-effect free on purpose: an instance can be constructed for `--help` or
injected in a test without creating anything. Directories are created by the atomic writer
performing an authorized mutation, never by asking where a file lives.
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
        # roaming=False keeps credentials off a Windows roaming profile.
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
        # Data, not config: the fallback credential file must not be synced or shared as a
        # settings file, and must never sit in the cache the CLI may clear.
        return self.data_root / "credentials.json"

    def manifests_dir(self) -> Path:
        # Cached manifests are re-fetchable, so they belong in cache and may be evicted;
        # this is what lets `harness <name> --help` work offline.
        return self.cache_root / "manifests"

    def operations_dir(self) -> Path:
        return self.state_root / "operations"

    def legacy_config_file(self) -> Path:
        return self.legacy_root / "config.json"

    def legacy_credentials_file(self) -> Path:
        return self.legacy_root / "credentials.json"

    def legacy_manifests_dir(self) -> Path:
        return self.legacy_root / "manifests"
