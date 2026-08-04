"""Public typed-error contracts. Importing this pulls in Click and the output layer.

Keep it out of the minimal `import vidbyte_cli` path: the package root resolves a version
without loading command or presentation dependencies. Concrete failures live in
`failures.py` and are imported from there directly by the code that raises them.
"""

from .cli_error import CliError
from .codes import CliErrorCode, ExitCode
from .handler import ErrorHandler

__all__ = ["CliError", "CliErrorCode", "ErrorHandler", "ExitCode"]
