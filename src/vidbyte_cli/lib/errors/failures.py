"""One CliError subclass per failure the platform can raise, prose included.

This is where the agent-native `description` and `trace` text lives. Keeping it here rather
than at the raise site means a caller writes `raise EmptyPrompt()` in one line, two commands
that fail the same way cannot drift apart, and the wording is reviewable in one place.

Nothing in this file may embed a secret: `description` and `trace` are static authored text
and must stay independent of credentials, prompt bodies, and backend response content.
"""

from __future__ import annotations

from .cli_error import CliError
from .codes import CliErrorCode, ExitCode


class NotImplementedFeature(CliError):
    """A scaffolded command or service with no implementation in this release."""

    code = CliErrorCode.NOT_IMPLEMENTED
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, subject: str) -> None:
        super().__init__(
            f"{subject} is not implemented yet.",
            description=(
                f"The CLI recognizes {subject} and parsed the invocation successfully, but the "
                "behavior behind it has not shipped in this release. Nothing was sent to the "
                "Vidbyte backend and no local state changed. Changing arguments or retrying "
                "will not help until the implementing release lands."
            ),
            trace=(
                "CliApplication.run built the static command tree, Click matched and validated "
                "this command, and the command callback reached its unimplemented body."
            ),
            hint="Check the CLI release notes for availability.",
        )


class InvalidCommandUsage(CliError):
    """Click rejected the invocation before any command body ran."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, message: str, command_path: str, exit_code: int, cause: Exception) -> None:
        super().__init__(
            message,
            description=(
                "The command line did not match the declared command tree, so parsing stopped "
                "before any command ran. The wording comes from Click and names only parser "
                "values, never user data. No backend request was made and no local state "
                "changed. Correct the invocation and run it again."
            ),
            trace=(
                "CliApplication.run built the command tree and delegated to Click, which "
                "rejected the arguments while resolving the command and its parameters."
            ),
            exit_code=exit_code,
            hint=f"Run '{command_path} --help' for usage.",
            cause=cause,
        )


class ConflictingOutputFormat(CliError):
    """`--json` was combined with an incompatible `--format` value."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "--json conflicts with the selected --format value.",
            description=(
                "`--json` is exactly an alias for `--format json`, so pairing it with any other "
                "format asks for two different result encodings on one stream. The CLI refuses "
                "rather than silently picking a winner, because a machine consumer cannot "
                "detect the substitution. Pass one of the two flags."
            ),
            trace=(
                "CliApplication.run resolved root output policy through "
                "RootOptionInspector/_resolve_output_format before constructing any service."
            ),
            hint="Remove --json or use --format json.",
        )


class OperationInterrupted(CliError):
    """The invocation was cancelled by the user or an abort."""

    code = CliErrorCode.INTERRUPTED
    exit_status = ExitCode.INTERRUPTED

    def __init__(self) -> None:
        super().__init__(
            "Operation interrupted.",
            description=(
                "Ctrl-C or a Click abort ended the invocation before it completed. Work already "
                "submitted to the Vidbyte backend is not cancelled by this signal and may still "
                "be running. Status 130 is the conventional shell code for an interrupt, so a "
                "caller can tell cancellation apart from failure."
            ),
            trace=(
                "The interrupt reached the CliApplication.run boundary from wherever the "
                "invocation was waiting — argument parsing, prompting, or command execution."
            ),
        )


class UnexpectedInternalError(CliError):
    """An unclassified exception reached the application boundary."""

    code = CliErrorCode.INTERNAL_ERROR
    exit_status = ExitCode.SOFTWARE

    def __init__(self, cause: Exception | None) -> None:
        super().__init__(
            "An unexpected internal error occurred.",
            description=(
                "An exception escaped without being classified by the code that raised it, so "
                "this is a CLI defect rather than an invocation mistake. The original exception "
                "value is withheld because it may quote a credential, a prompt, or a backend "
                "response body. The command's effect is unknown; verify state before retrying."
            ),
            trace=(
                "ErrorHandler.handle received an exception that matched neither CliError, nor a "
                "Click exception, nor an interrupt, at the CliApplication.run boundary."
            ),
            hint="Retry with --debug for a redacted stack trace.",
            cause=cause,
        )


class AuthenticationRequired(CliError):
    """A command needing the Vidbyte API reached a machine with no stored credential."""

    code = CliErrorCode.AUTH_REQUIRED
    exit_status = ExitCode.AUTHENTICATION

    def __init__(self) -> None:
        super().__init__(
            "Authentication is required.",
            description=(
                "The command needs a Vidbyte API key and the credential store held none for "
                "this machine. Authentication is checked before repository inspection and "
                "before any network call, so nothing was read or submitted. Log in once and "
                "the key is reused by every later invocation."
            ),
            trace=(
                "BaseHarness.dispatch called HarnessContext.require_api_key, which read the "
                "credential store and found no stored key."
            ),
            hint="Run 'vidbyte-cli login' first.",
        )


class HarnessInvocationFailed(CliError):
    """An unclassified failure escaped the generic harness lifecycle."""

    code = CliErrorCode.OPERATION_FAILED
    exit_status = ExitCode.OPERATIONAL_FAILURE
    retryable = True

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "The harness invocation failed.",
            description=(
                "The harness run was submitted or polled and the backend lifecycle raised "
                "something the CLI cannot yet classify. The underlying exception is withheld "
                "because transport errors routinely quote URLs, headers, and response bodies. "
                "This class of failure is usually transient, so retrying is reasonable."
            ),
            trace=(
                "BaseHarness.dispatch authenticated, translated the command through "
                "InvocationBuilder, and called a harness endpoint, whose failure reached "
                "map_harness_error."
            ),
            hint="Retry the command. If the problem continues, use --debug for redacted details.",
            cause=cause,
        )


class MissingHarnessArgument(CliError):
    """A declared required harness argument was absent from the invocation."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, command: str, argument: str) -> None:
        super().__init__(
            f"Missing required argument '{argument}' for command '{command}'.",
            description=(
                f"The harness manifest declares '{argument}' as required for '{command}', and "
                "the parsed invocation supplied no value for it. Nothing was submitted to the "
                "backend. Status 2 separates this caller-side mistake from an operational "
                "failure, so an agent can correct the call and retry immediately."
            ),
            trace=(
                "BaseHarness.dispatch delegated to InvocationBuilder.build, which mapped Click's "
                "flat parameters onto the declared arguments and found this one unset."
            ),
            hint=f"Pass it positionally, e.g. `{command} <{argument}>`.",
        )


class AmbiguousPromptSource(CliError):
    """More than one prompt source was supplied for a single run."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "Provide exactly one prompt source.",
            description=(
                "A positional prompt and --prompt-file were both supplied, and the CLI will not "
                "guess which one the caller meant. Silently preferring one would make the same "
                "command line mean different things across releases. Neither source was read, "
                "so no file was opened and stdin was not consumed."
            ),
            trace=(
                "The command adapter called PromptInputResolver.resolve, which checks source "
                "exclusivity before touching any external input."
            ),
            hint="Use a positional prompt, --prompt-file PATH, or '-' for stdin.",
        )


class MissingPrompt(CliError):
    """No prompt source was supplied and prompting is not implied by redirection."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "A prompt is required.",
            description=(
                "The command needs prompt text and none of the three accepted sources was "
                "supplied. Stdin is read only when '-' is passed explicitly, so a command whose "
                "input happens to be redirected fails here instead of hanging on a read that "
                "will never complete. Nothing was submitted to the backend."
            ),
            trace=(
                "The command adapter called PromptInputResolver.resolve, which found neither a "
                "positional value nor --prompt-file."
            ),
            hint="Pass a positional prompt, --prompt-file PATH, or '-' for stdin.",
        )


class PromptFileUnreadable(CliError):
    """The path given to --prompt-file could not be opened or read."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(
            f"Unable to read prompt file '{path}'.",
            description=(
                "The path passed to --prompt-file could not be opened for reading. It is "
                "typically missing, a directory, or blocked by filesystem permissions. The "
                "operating system's own message is withheld because it can expose unrelated "
                "filesystem layout. Nothing was submitted to the backend."
            ),
            trace=(
                "PromptInputResolver.resolve selected the file source and _read_file attempted "
                "to open the path in UTF-8 text mode."
            ),
            hint="Check that the path exists and is a readable file.",
            cause=cause,
        )


class PromptFileNotUtf8(CliError):
    """The prompt file exists but is not valid UTF-8 text."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "The prompt file must contain valid UTF-8 text.",
            description=(
                "The file opened but its bytes did not decode as UTF-8. The CLI pins UTF-8 "
                "rather than following the host locale so the same file produces the same run "
                "on every machine. Re-save the file as UTF-8, or pass the prompt positionally. "
                "No decoded content is echoed, because the file may hold sensitive text."
            ),
            trace=(
                "PromptInputResolver.resolve selected the file source and _read_file decoded "
                "the opened handle as UTF-8."
            ),
            cause=cause,
        )


class StandardInputNotText(CliError):
    """Explicit stdin was requested but could not be decoded as text."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "Standard input must contain valid text.",
            description=(
                "'-' selected stdin as the prompt source, but the bytes arriving on that stream "
                "did not decode as text. This usually means binary content was piped in, or the "
                "producing process used an incompatible encoding. No content is echoed back, "
                "because piped input may hold sensitive text."
            ),
            trace=(
                "PromptInputResolver.resolve matched the '-' stdin marker and _read_stdin read "
                "a bounded amount from the injected stdin stream."
            ),
            cause=cause,
        )


class EmptyPrompt(CliError):
    """The resolved prompt held no non-whitespace content."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "The prompt must not be empty.",
            description=(
                "The prompt source resolved successfully but contained only whitespace. An "
                "empty prompt would consume credits for a run that cannot produce a useful "
                "result, so it is rejected before submission. A file source that looks correct "
                "in an editor may be empty because it was written but never flushed."
            ),
            trace=(
                "PromptInputResolver.resolve read the selected source and passed the value to "
                "_validate, which checks content before length."
            ),
        )


class PromptTooLong(CliError):
    """The resolved prompt exceeded the CLI's bounded input limit."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, limit: int) -> None:
        super().__init__(
            f"The prompt exceeds the {limit}-character limit.",
            description=(
                f"The resolved prompt was longer than the {limit}-character bound the CLI reads "
                "from any source. The limit exists so a large or runaway file cannot be read "
                "into memory in full before validation. Only the length is reported; the prompt "
                "itself is never quoted back. Shorten the prompt or split the work into runs."
            ),
            trace=(
                "PromptInputResolver.resolve read one character past the limit from the selected "
                "source and passed the value to _validate."
            ),
        )
