"""Runtime contracts that are safe to import from the package root.

CliApplication and ApplicationContext are intentionally NOT re-exported: importing
`vidbyte_cli` must not pull in click commands, HTTP models, or harness policy.
"""

from .version import VersionProvider, current_version

__all__ = ["VersionProvider", "current_version"]
