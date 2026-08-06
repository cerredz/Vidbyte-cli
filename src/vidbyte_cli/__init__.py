"""Universal Vidbyte CLI.

Import-side-effect free on purpose: importing this package must not build commands, read
credentials, or touch the network.
"""

from .lib.runtime.version import current_version

__version__ = current_version()

__all__ = ["__version__"]
