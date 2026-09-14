"""Offline verification for actionable connection login failures."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import vidbyte_cli.cli  # noqa: E402, F401
from vidbyte_cli.lib.connections.oauth import OAuthCallbackServer  # noqa: E402
from vidbyte_cli.lib.connections.providers.google_drive import (  # noqa: E402
    GoogleDriveConnectionAdapter,
)
from vidbyte_cli.lib.connections.providers.slack import (  # noqa: E402
    SlackConnectionAdapter,
)
from vidbyte_cli.lib.errors.codes import CliErrorCode  # noqa: E402
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    ConnectionAuthenticationRequired,
    ConnectionCallbackTimeout,
    ConnectionLoopbackUnavailable,
    ConnectionOAuthFailed,
    ConnectionOAuthStateInvalid,
    ConnectionRateLimited,
    ConnectionReauthenticationRequired,
    ConnectionSaveFailed,
    ConnectionScopeInsufficient,
    ConnectionStoreUnavailable,
    GitHubAccessDenied,
    GitHubClientInvalid,
    GitHubDeviceCodeExpired,
    GoogleAccessDenied,
    GoogleClientInvalid,
    GoogleInvalidGrant,
    GoogleScopeInvalid,
    SlackAccessDenied,
    SlackClientInvalid,
    SlackInvalidGrant,
)


class Results:
    """Counts labeled PASS/FAIL lines for the failure taxonomy."""

    def __init__(self) -> None:
        # Separate counters keep one failure from hiding later ones.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool) -> None:
        # Prints one searchable line per design-plan case.
        if condition:
            self.passed += 1
            print(f"PASS {name}")
        else:
            self.failed += 1
            print(f"FAIL {name}")

    def summary(self) -> int:
        # Reports the total and selects the exit status.
        total = self.passed + self.failed
        print(f"{self.passed}/{total} tests passed")
        return 0 if self.failed == 0 else 1


def raises(func: Any, exc: Any) -> Any:
    # Runs one callable and returns the error or None.
    try:
        func()
    except exc as error:
        return error
    except Exception:
        return None
    return None


def main() -> int:
    # Runs every Section 10 mapping case without network access.
    results = Results()
    slack = SlackConnectionAdapter()
    drive = GoogleDriveConnectionAdapter()

    err = raises(
        lambda: slack._validate_callback({"state": "s", "error": "access_denied"}, "s"),
        SlackAccessDenied,
    )
    results.check("slack-denied-callback", isinstance(err, SlackAccessDenied))
    results.check(
        "slack-denied-code", err is not None and err.code.value == "CONNECTION_OAUTH_FAILED"
    )

    err = raises(
        lambda: slack._validate_callback({"state": "bad"}, "s"), ConnectionOAuthStateInvalid
    )
    results.check("slack-state-first", isinstance(err, ConnectionOAuthStateInvalid))

    err = raises(
        lambda: slack._require_ok({"ok": False, "error": "invalid_code"}), SlackInvalidGrant
    )
    results.check("slack-invalid-grant", isinstance(err, SlackInvalidGrant))

    err = raises(
        lambda: slack._require_ok({"ok": False, "error": "ratelimited"}), ConnectionRateLimited
    )
    results.check("slack-ratelimited", isinstance(err, ConnectionRateLimited) and err.retryable)

    err = raises(
        lambda: slack._require_ok({"ok": False, "error": "rate_limited"}), ConnectionRateLimited
    )
    results.check("slack-ratelimited-variant", isinstance(err, ConnectionRateLimited))

    err = raises(
        lambda: slack._require_ok({"ok": False, "error": "invalid_client"}), SlackClientInvalid
    )
    results.check("slack-client-invalid", isinstance(err, SlackClientInvalid))
    results.check(
        "slack-client-code",
        err is not None and err.code == CliErrorCode.CONNECTION_CONFIGURATION_INVALID,
    )

    err = raises(
        lambda: slack._require_ok({"ok": False, "error": "future_x"}), ConnectionOAuthFailed
    )
    results.check("slack-unknown-generic", isinstance(err, ConnectionOAuthFailed))

    err = raises(
        lambda: drive._validate_callback({"state": "s", "error": "access_denied"}, "s"),
        GoogleAccessDenied,
    )
    results.check("google-denied-callback", isinstance(err, GoogleAccessDenied))

    err = raises(
        lambda: drive._raise_for_token_error({"error": "invalid_grant"}), GoogleInvalidGrant
    )
    results.check("google-invalid-grant", isinstance(err, GoogleInvalidGrant))

    err = raises(
        lambda: drive._raise_for_token_error({"error": "invalid_client"}), GoogleClientInvalid
    )
    results.check("google-client-invalid", isinstance(err, GoogleClientInvalid))

    err = raises(
        lambda: drive._raise_for_token_error({"error": "invalid_scope"}), GoogleScopeInvalid
    )
    results.check("google-scope-invalid", isinstance(err, GoogleScopeInvalid))
    results.check(
        "google-scope-code",
        err is not None and err.code == CliErrorCode.CONNECTION_SCOPE_INSUFFICIENT,
    )

    err = raises(lambda: drive._raise_for_token_error({"error": "mystery"}), ConnectionOAuthFailed)
    results.check("google-unknown-generic", isinstance(err, ConnectionOAuthFailed))
    results.check("google-no-error-passes", drive._raise_for_token_error({}) is None)

    err = raises(lambda: OAuthCallbackServer("slack").wait(0.05), ConnectionCallbackTimeout)
    results.check("loopback-timeout", isinstance(err, ConnectionCallbackTimeout))

    err = raises_bind_failure()
    results.check("loopback-bind", isinstance(err, ConnectionLoopbackUnavailable))

    err = raises_save_failure()
    results.check("manager-save-failed", isinstance(err, ConnectionSaveFailed))
    results.check(
        "manager-save-words", err is not None and "grant succeeded" in err.message.lower()
    )

    pairs: list[tuple[Any, str]] = [
        (GitHubAccessDenied, "CONNECTION_OAUTH_FAILED"),
        (GitHubDeviceCodeExpired, "CONNECTION_OAUTH_FAILED"),
        (GitHubClientInvalid, "CONNECTION_CONFIGURATION_INVALID"),
        (SlackAccessDenied, "CONNECTION_OAUTH_FAILED"),
        (SlackInvalidGrant, "CONNECTION_OAUTH_FAILED"),
        (SlackClientInvalid, "CONNECTION_CONFIGURATION_INVALID"),
        (GoogleAccessDenied, "CONNECTION_OAUTH_FAILED"),
        (GoogleInvalidGrant, "CONNECTION_OAUTH_FAILED"),
        (GoogleClientInvalid, "CONNECTION_CONFIGURATION_INVALID"),
        (GoogleScopeInvalid, "CONNECTION_SCOPE_INSUFFICIENT"),
    ]
    for cls, code in pairs:
        inst = cls()
        text = inst.message + inst.description + str(inst.hint) + inst.trace
        leak = ("access_token" in text) or ("refresh_token" in text) or ("code_verifier" in text)
        results.check(f"no-secret-{cls.__name__}", (not leak) and inst.code.value == code)
        results.check(f"hint-{cls.__name__}", bool(inst.hint) and len(str(inst.hint)) > 12)

    results.check("typed-reauth", issubclass(ConnectionReauthenticationRequired, Exception))
    results.check("typed-auth", issubclass(ConnectionAuthenticationRequired, Exception))
    results.check("typed-scope", issubclass(ConnectionScopeInsufficient, Exception))
    results.check("typed-store", issubclass(ConnectionStoreUnavailable, Exception))
    results.check("typed-state", issubclass(ConnectionOAuthStateInvalid, Exception))
    return results.summary()


def raises_bind_failure() -> Any:
    # Forces the loopback bind-failure branch without real sockets.
    import vidbyte_cli.lib.connections.oauth as oauth_module

    real = oauth_module._CallbackHTTPServer

    def fail_bind(*args: Any, **kwargs: Any) -> Any:
        # Simulates an occupied or blocked localhost port.
        raise OSError("address in use")

    oauth_module._CallbackHTTPServer = fail_bind  # type: ignore[assignment]
    try:
        return raises(lambda: OAuthCallbackServer("slack"), ConnectionLoopbackUnavailable)
    finally:
        oauth_module._CallbackHTTPServer = real


def raises_save_failure() -> Any:
    # Proves a verified grant that cannot persist reports save-failed.
    import shutil
    import tempfile

    from pydantic import SecretStr

    import vidbyte_cli.types.connection as conn_types
    from vidbyte_cli.lib.config.paths import VidbytePaths
    from vidbyte_cli.lib.connections.manager import ConnectionManager
    from vidbyte_cli.lib.connections.store import ConnectionKeyringStore, ConnectionStore
    from vidbyte_cli.lib.io import IOStreams
    from vidbyte_cli.lib.runtime.context import ApplicationContext
    from vidbyte_cli.types.connection import ConnectionProvider

    tmp = Path(tempfile.mkdtemp(prefix="vidbyte-save-fail-"))
    try:
        paths = VidbytePaths(tmp / "c", tmp / "ca", tmp / "s", tmp / "d", tmp / "l")
        streams = IOStreams(io.StringIO(), io.StringIO(), io.StringIO())
        context = ApplicationContext(streams, environment={}, paths=paths)
        manager = ConnectionManager(context)
        manager._store = ConnectionStore(paths, ConnectionKeyringStore(_FailingKeyring()))  # type: ignore[arg-type]
        token = conn_types.ConnectionToken(access_token=SecretStr("a" * 16))
        identity = conn_types.ConnectionIdentity(provider=ConnectionProvider.GITHUB, account_id="1")
        holder = _Holder(token, identity)
        manager._adapter = lambda provider: _FakeAdapter(holder)  # type: ignore[assignment]
        manager._profile = lambda: "default"  # type: ignore[assignment]
        return raises(
            lambda: manager.login(ConnectionProvider.GITHUB, "gh", ()), ConnectionSaveFailed
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _FailingKeyring:
    """Keyring backend that fails every write for save-failure tests."""

    priority = 5.0

    def get_password(self, service: str, username: str) -> str | None:
        # Reads always miss so the write path is under test.
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        # Simulates a locked or missing OS keyring during save.
        raise OSError("keyring locked")

    def delete_password(self, service: str, username: str) -> None:
        # Deletion is unused in the save-failure path.
        return None


class _Holder:
    """Canned verified grant returned by the stubbed adapter."""

    def __init__(self, token: Any, identity: Any) -> None:
        # Holds the token and identity the fake login returns.
        self.token = token
        self.identity = identity


class _FakeAdapter:
    """Adapter stub returning one canned verified grant."""

    def __init__(self, authenticated: Any) -> None:
        # Holds the canned grant returned by the stubbed login.
        self._authenticated = authenticated

    def login(self, context: Any, scopes: Any, path: Any = None) -> Any:
        # Returns the canned grant without touching any provider.
        return self._authenticated


if __name__ == "__main__":
    raise SystemExit(main())
