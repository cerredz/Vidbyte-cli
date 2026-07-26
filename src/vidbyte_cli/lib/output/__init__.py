"""FILE: src/vidbyte_cli/lib/output/__init__.py

PURPOSE: Publishes the stable output-format, document, and manager contracts used across
runtime and feature packages. Implementation helpers remain private to their modules.

ROLE IN CODEBASE: ApplicationContext and feature presenters import from this facade.
formats.py, models.py, and manager.py supply the exported implementations without creating
process-global output state.

ARCHITECTURE NOTE: Explicit exports make the presentation boundary discoverable while
keeping terminal detection in lib/io and exception mapping in lib/errors.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ColorMode, OutputFormat: root presentation preferences.
- OutputDocument: versioned machine record.
- OutputManager, OutputPolicy: invocation-owned stream behavior and input policy.

COMMON MODIFICATION PATTERNS: Re-export a contract only when multiple packages use it and
after recording its ownership in output/README.md.

WHAT NOT TO DO IN THIS FILE:
1. Do not instantiate OutputManager or bind system streams.
2. Do not export feature-specific presenters.
3. Do not perform serialization at import time.

KNOWN EDGE CASES: This facade imports Pydantic-backed documents and is not part of the
minimal top-level `import vidbyte_cli` path.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md
documents the output boundary.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises these exports through runtime composition.
"""

from .formats import ColorMode, OutputFormat
from .manager import OutputManager, OutputPolicy
from .models import OutputDocument

__all__ = ["ColorMode", "OutputDocument", "OutputFormat", "OutputManager", "OutputPolicy"]
