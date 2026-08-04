"""The user-safe exception every command and service raises instead of printing.

A CliError serves two callers at once. A human gets `message` and `hint`; an agent also gets
the non-sensitive `description`/`trace`/`file_path` triple, which is what lets it repair its
own invocation without a transcript. Subclasses in `failures.py` own that prose, so a raise
site stays one line and every failure of a kind reads identically.

`cause` is the one field that may hold backend, credential, or filesystem detail. It is
private on purpose: no renderer may serialize it, and debug traces show frames only.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import FrameType
from typing import ClassVar

from .codes import CliErrorCode, ExitCode

# Frames inside this package are error plumbing, never the site that actually failed.
_ERRORS_PACKAGE = Path(__file__).resolve().parent
# `.../vidbyte_cli/lib/errors` -> the directory holding the package, so reported paths are
# relative and identical whether the CLI runs from a checkout or an installed wheel.
_PACKAGE_PARENT = _ERRORS_PACKAGE.parents[2]


class CliError(Exception):
    """A classified CLI failure whose message and metadata are safe to display."""

    # Subclasses fix the classification; only Click may override exit_code per instance.
    code: ClassVar[CliErrorCode] = CliErrorCode.OPERATION_FAILED
    exit_status: ClassVar[ExitCode] = ExitCode.OPERATIONAL_FAILURE
    retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        description: str,
        trace: str,
        *,
        exit_code: int | None = None,
        hint: str | None = None,
        request_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.description = description
        self.trace = trace
        self.file_path = self._origin_file()
        self.exit_code = int(self.exit_status if exit_code is None else exit_code)
        self.hint = hint
        self.request_id = request_id
        self.cause = cause

    @property
    def code_value(self) -> str:
        # Output protocols depend on a plain string without importing this enum package.
        return self.code.value

    @staticmethod
    def _origin_file() -> str:
        # An agent's next action is opening a file, and a path hand-written per subclass goes
        # stale the moment code moves. The first frame outside this package is the command or
        # service that actually failed, so derive it instead of declaring it.
        frame: FrameType | None = inspect.currentframe()
        while frame is not None:
            # Resolve before comparing: a frame's filename may be relative to the cwd.
            path = Path(frame.f_code.co_filename).resolve()
            if path.parent != _ERRORS_PACKAGE:
                return CliError._package_path(path)
            frame = frame.f_back
        return CliError._package_path(Path(__file__).resolve())

    @staticmethod
    def _package_path(path: Path) -> str:
        # Frames outside the package (Click, the interpreter) have no meaningful repository
        # location, so report the bare filename rather than an absolute machine path.
        if not path.is_relative_to(_PACKAGE_PARENT):
            return path.name
        return path.relative_to(_PACKAGE_PARENT).as_posix()
