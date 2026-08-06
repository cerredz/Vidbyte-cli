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


class ConfigUnreadable(CliError):
    """The stored configuration file could not be parsed against the version-one schema."""

    code = CliErrorCode.CONFIG_INVALID
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(
            "CLI configuration is invalid or uses an unsupported schema.",
            description=(
                "The configuration file exists but did not validate: it is unreadable, is not "
                "JSON, exceeds the size bound, or declares a schema version this release does "
                "not implement. The CLI never repairs or overwrites a file it cannot "
                "understand, so nothing was changed and no command ran."
            ),
            trace=(
                "ConfigStore.load selected the native or legacy configuration path and _read "
                "decoded its bytes and validated them as a ConfigDocument."
            ),
            hint=f"Repair or move the configuration file at {path}.",
            cause=cause,
        )


class ConfigInvalidBeforeWrite(CliError):
    """The configuration on disk stopped validating between this command's read and write."""

    code = CliErrorCode.CONFIG_INVALID
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(
            "CLI configuration changed to an invalid or unsupported schema.",
            description=(
                "The configuration validated when this command read it and no longer does, so "
                "another process or a manual edit replaced it mid-command. The write was "
                "abandoned before touching the file: the new content is intact and the setting "
                "you asked for was not applied."
            ),
            trace=(
                "ConfigStore.save called _native_digest to re-read the current file for "
                "conflict detection, and that re-read failed validation."
            ),
            hint=f"Repair or move the configuration file at {path}.",
            cause=cause,
        )


class ConfigWriteConflict(CliError):
    """The configuration file changed after this command read it."""

    code = CliErrorCode.CONFIG_WRITE_CONFLICT
    exit_status = ExitCode.OPERATIONAL_FAILURE
    retryable = True

    def __init__(self) -> None:
        super().__init__(
            "CLI configuration changed during this command.",
            description=(
                "Writing a setting is a read-modify-write, and the file no longer matches what "
                "this command read. Completing the write would silently discard whatever the "
                "other writer stored. Nothing was written, so the other change is intact and "
                "re-running against the current file is safe."
            ),
            trace=(
                "ConfigStore.save compared the digest captured by the caller's read against a "
                "fresh digest of the native configuration file and found them different."
            ),
            hint="Run the command again against the latest configuration.",
        )


class InvalidConfigValue(CliError):
    """`config set` was given a value the field's schema rejects."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self, field: str, cause: Exception) -> None:
        super().__init__(
            f"Invalid value for configuration field '{field}'.",
            description=(
                f"The value supplied for '{field}' failed the same validation the persisted "
                "document uses, so accepting it would write a profile the CLI could not load "
                "back. Nothing was written. The underlying validation detail is withheld "
                "because it quotes the value, which may have been mistyped from a secret."
            ),
            trace=(
                "ConfigSetCommand.execute called ConfigStore.set, whose _updated_profile "
                "revalidated the whole profile with the new field value applied."
            ),
            hint="Run 'vidbyte-cli config get' to inspect the current profile value.",
            cause=cause,
        )


class InvalidConfigOverride(CliError):
    """An environment or command-line configuration value could not be parsed."""

    code = CliErrorCode.CONFIG_INVALID
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "An environment or command configuration value is invalid.",
            description=(
                "Resolution combines command options, VIDBYTE_* variables, and the selected "
                "profile, and one supplied value did not parse into its declared type. The "
                "offending value is not echoed, because variables in the same namespace hold "
                "credentials. No command ran and no local state changed."
            ),
            trace=(
                "ConfigResolver.resolve applied command → environment → profile precedence per "
                "field and constructed the ResolvedConfig from the winning values."
            ),
            hint="Check VIDBYTE_* settings and the selected CLI profile.",
            cause=cause,
        )


class StateWriteThroughSymlink(CliError):
    """A local state path the CLI was about to replace is a symbolic link."""

    code = CliErrorCode.CONFIG_INVALID
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self) -> None:
        super().__init__(
            "Refusing to write CLI state through a symbolic link.",
            description=(
                "The target path is a symbolic link, and the CLI writes state by replacing a "
                "file atomically. Whether that replaces the link or the file it points at "
                "varies by platform, which is not a strong enough guarantee for a path that "
                "may hold a credential. Nothing was written and the link is untouched."
            ),
            trace=(
                "A store encoded its document and called AtomicFileWriter.write, which checks "
                "the destination for a symbolic link before creating its temporary sibling."
            ),
            hint="Replace the symbolic link with a regular file and retry.",
        )


class StateWriteFailed(CliError):
    """The operating system refused a local state write."""

    code = CliErrorCode.OPERATION_FAILED
    exit_status = ExitCode.OPERATIONAL_FAILURE
    retryable = True

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "CLI state could not be saved.",
            description=(
                "Creating, flushing, or replacing the state file failed at the filesystem "
                "level — typically permissions, a read-only or full volume, or a parent "
                "directory the CLI may not create. The temporary sibling was removed, so the "
                "previous file is intact and the operation had no partial effect."
            ),
            trace=(
                "AtomicFileWriter.write created a randomized sibling file, wrote and fsynced "
                "it, and attempted os.replace onto the destination."
            ),
            hint="Check directory ownership and available disk space, then retry.",
            cause=cause,
        )


class MigrationVerificationFailed(CliError):
    """Legacy state was copied but the copy did not read back identically."""

    code = CliErrorCode.OPERATION_FAILED
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self) -> None:
        super().__init__(
            "Legacy CLI state could not be verified after migration.",
            description=(
                "Migration copies each item and reads it back to prove the copy is identical, "
                "and one read-back disagreed. Migration never deletes, so the legacy tree under "
                "~/.vidbyte is exactly as it was. The native location may hold a partial copy, "
                "which later runs overwrite rather than trust."
            ),
            trace=(
                "StateMigration.migrate_if_needed copied configuration, manifests, or the "
                "legacy credential and compared each destination against its source."
            ),
            hint="The legacy files were preserved; retry after checking local storage.",
        )


class CredentialStoreUnavailable(CliError):
    """The operating-system keyring could not be used for this operation."""

    code = CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, cause: Exception | None = None) -> None:
        super().__init__(
            "The operating-system credential store is unavailable.",
            description=(
                "No keyring backend reported itself usable, or the backend rejected the "
                "operation — a locked keychain, a headless session with no agent, or a write "
                "that did not read back as written. The backend's own message is withheld "
                "because it can quote account identifiers. No credential was stored or read."
            ),
            trace=(
                "KeyringCredentialStore resolved the active backend and performed a scoped "
                "get, set, or delete against the 'vidbyte-cli' service."
            ),
            hint="Check the system keyring, or explicitly approve the restricted-file fallback.",
            cause=cause,
        )


class NoApprovedCredentialStore(CliError):
    """No keyring exists and restricted-file storage was not approved."""

    code = CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self) -> None:
        super().__init__(
            "No usable OS credential store is available.",
            description=(
                "The key verified successfully but has nowhere approved to live. This machine "
                "exposes no working keyring, and the restricted-file fallback keeps the key "
                "readable to your account, so the CLI will not select it on your behalf. "
                "Nothing was written; the verified key was discarded with this process."
            ),
            trace=(
                "LoginCommand.execute verified the credential and called CredentialStore.write, "
                "which found no available keyring and no file-fallback consent."
            ),
            hint="Retry login and explicitly approve the restricted-file fallback.",
        )


class StoredCredentialUnreadable(CliError):
    """The restricted fallback credential file could not be parsed."""

    code = CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "Stored CLI credentials are invalid or unavailable.",
            description=(
                "The fallback credential file exists but is unreadable, is not JSON, exceeds "
                "the size bound, or declares an unsupported schema version. The CLI will not "
                "rewrite a credential file it cannot understand, because that could destroy a "
                "key it merely failed to parse. No credential was resolved."
            ),
            trace=(
                "FileCredentialStore._load read the restricted credential file and validated "
                "it as a version-one CredentialDocument."
            ),
            hint="Move the fallback credential file and run 'vidbyte-cli login' again.",
            cause=cause,
        )


class LegacyCredentialUnreadable(CliError):
    """The ~/.vidbyte credential file exists but could not be validated."""

    code = CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "Legacy CLI credentials are invalid or unavailable.",
            description=(
                "A credential file remains at the historical ~/.vidbyte location and did not "
                "validate, so it can be neither read nor migrated. It is reported rather than "
                "skipped, because ignoring it would leave a file that looks like a working "
                "login. It was not modified or removed."
            ),
            trace=(
                "A credential read or migration reached the legacy credential path and decoded "
                "its bytes as a Credentials document."
            ),
            hint="Run 'vidbyte-cli login' to replace the stored credential.",
            cause=cause,
        )


class LegacyCredentialSymlink(CliError):
    """Logout was asked to remove a legacy credential file that is a symbolic link."""

    code = CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self) -> None:
        super().__init__(
            "Refusing to remove legacy credentials through a symbolic link.",
            description=(
                "Logout deletes the legacy credential file so a stale key cannot become active "
                "again, but that path is a symbolic link: unlinking it would remove the link "
                "and leave whatever it points at. The CLI will not guess which one was meant. "
                "The scoped keyring and fallback entries were still cleared."
            ),
            trace=(
                "LogoutCommand.execute called CredentialStore.clear, whose clear_legacy step "
                "checked the legacy credential path before unlinking it."
            ),
            hint="Remove the symbolic link manually after verifying its target.",
        )


class LegacyCredentialRemovalFailed(CliError):
    """The legacy credential file could not be deleted during logout."""

    code = CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE
    retryable = True

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            "Legacy credentials could not be removed.",
            description=(
                "The legacy credential file exists and the filesystem refused to unlink it, "
                "usually because of directory permissions or another process holding it open. "
                "This is a failure rather than a skip, because the file can still authenticate "
                "later invocations. Scoped credentials were already cleared."
            ),
            trace=(
                "LogoutCommand.execute called CredentialStore.clear, whose clear_legacy step "
                "attempted to unlink the legacy credential path."
            ),
            hint="Check the legacy file permissions and retry logout.",
            cause=cause,
        )


class InvalidEnvironmentApiKey(CliError):
    """VIDBYTE_API_KEY is set but holds nothing usable."""

    code = CliErrorCode.AUTH_REQUIRED
    exit_status = ExitCode.AUTHENTICATION

    def __init__(self) -> None:
        super().__init__(
            "VIDBYTE_API_KEY is empty or invalid.",
            description=(
                "The environment variable is set to an empty, whitespace-only, or oversized "
                "value. Because it is set it outranks the keyring and the fallback file, so "
                "falling through to stored credentials would authenticate as somebody the "
                "caller did not ask for. The value is never echoed back."
            ),
            trace=(
                "CredentialResolver.resolve read VIDBYTE_API_KEY from the injected environment "
                "and bounds-checked it before any store was consulted."
            ),
            hint="Set a valid key or remove the variable to use stored credentials.",
        )


class CredentialVerificationUnavailable(CliError):
    """This build has no verifier, so no credential may be persisted."""

    code = CliErrorCode.API_UNAVAILABLE
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self) -> None:
        super().__init__(
            "Credential verification is unavailable in this CLI build.",
            description=(
                "Login stores a key only after the backend confirms it, and the HTTP client "
                "that performs that check ships in a later release. The CLI fails rather than "
                "storing an unverified key, so an invalid credential can never reach durable "
                "storage. Nothing was written and no request was made."
            ),
            trace=(
                "LoginCommand.execute read the token and called CredentialVerifier.verify, "
                "which ApplicationContext had bound to PendingCredentialVerifier."
            ),
            hint="Upgrade to the release that includes the reusable HTTP client.",
        )


class NoninteractiveLoginRequiresToken(CliError):
    """Login had no terminal to prompt on and no explicit token source."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "Login requires explicit token input in noninteractive mode.",
            description=(
                "The hidden prompt needs an interactive terminal, and this invocation has none "
                "or passed --no-input. Stdin is read only when --with-token says so, so a "
                "redirected stream is never consumed by accident and the command cannot hang "
                "on a read that will not complete. No credential was stored."
            ),
            trace=(
                "LoginCommand.execute called CredentialInput.read without the stdin marker, "
                "which checked --no-input and the detected terminal capabilities."
            ),
            hint="Pipe the token to 'vidbyte-cli login --with-token'.",
        )


class InvalidApiKeyInput(CliError):
    """The token supplied to login was empty or beyond the input bound."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "The supplied Vidbyte API key is empty or too large.",
            description=(
                "The value read from the prompt or from stdin was blank after trimming, or "
                "longer than the 4096-character bound the CLI reads from any secret source. "
                "That bound keeps an accidental file redirect from being pulled into memory as "
                "a key. The value is never echoed, and nothing was verified or stored."
            ),
            trace=(
                "CredentialInput.read consumed the selected input channel and bounds-checked "
                "the trimmed value before constructing Credentials."
            ),
            hint="Paste the key from the Vidbyte dashboard, or pipe it with --with-token.",
        )


class FileFallbackNotApproved(CliError):
    """Login could not ask for fallback consent and none was given on the command line."""

    code = CliErrorCode.INVALID_ARGUMENT
    exit_status = ExitCode.USAGE

    def __init__(self) -> None:
        super().__init__(
            "No OS keyring is available and file storage was not approved.",
            description=(
                "Storing the key would require the restricted-file fallback, which the CLI uses "
                "only with explicit consent. This invocation is noninteractive, so the "
                "confirmation prompt cannot be shown and consent has to arrive as a flag. "
                "Nothing was stored."
            ),
            trace=(
                "LoginCommand.execute called _fallback_consent, which found no available "
                "keyring, no --allow-file-fallback, and no interactive terminal."
            ),
            hint="Retry with --allow-file-fallback after reviewing the storage warning.",
        )
