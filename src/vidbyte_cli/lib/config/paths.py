"""Single source of truth for every path the CLI reads or writes under ~/.vidbyte."""

from __future__ import annotations

from pathlib import Path


class VidbytePaths:
    @staticmethod
    def root() -> Path:
        # The ~/.vidbyte directory that holds all CLI state.
        return Path.home() / ".vidbyte"

    @staticmethod
    def credentials_file() -> Path:
        # JSON file storing the user's Vidbyte API key.
        return VidbytePaths.root() / "credentials.json"

    @staticmethod
    def config_file() -> Path:
        # JSON file storing non-secret CLI configuration.
        return VidbytePaths.root() / "config.json"

    @staticmethod
    def manifests_dir() -> Path:
        # Cache directory for downloaded harness manifests, so `--help` works offline and
        # startup avoids a network round-trip when a manifest is already cached
        # (supports the two-pass namespace peek in cli.py).
        return VidbytePaths.root() / "manifests"
