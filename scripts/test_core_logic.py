"""Deterministic spec of retry policy, API problem mapping, and config precedence.

Run with `python scripts/test_core_logic.py`, or via `scripts/run_ci.py`. Cases call the real
units in process: no sockets, no keyring, no developer home directory. The two Retry-After
parsers are intentionally different and both are pinned; this file does not unify them.
"""

from __future__ import annotations

import random
import shutil
import sys
import tempfile
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402

from vidbyte_cli.lib.api.problem import ApiProblemMapper  # noqa: E402
from vidbyte_cli.lib.api.retry import RequestMetadata, RetryPolicy  # noqa: E402
from vidbyte_cli.lib.config import ConfigOverrides, ConfigResolver, ConfigStore  # noqa: E402
from vidbyte_cli.lib.config.models import (  # noqa: E402
    DEFAULT_API_URL,
    ConfigDocument,
    ConfigField,
    ConfigSource,
    ProfileConfig,
)
from vidbyte_cli.lib.config.paths import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.errors.codes import CliErrorCode, ExitCode  # noqa: E402
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    ApiCredentialsRejected,
    ApiCreditExhausted,
    ApiOperationFailed,
    ApiPermissionDenied,
    ApiRateLimited,
    ApiRequestConflicted,
    ApiRequestRejected,
    ApiResourceNotFound,
    ApiRouteMissing,
    ApiUnavailable,
    ApiUnreachable,
    InvalidConfigOverride,
)
from vidbyte_cli.lib.output import ColorMode, OutputFormat  # noqa: E402

_SECRET = "vb_live_" + "a" * 32
_PAST_HTTP_DATE = format_datetime(datetime(1970, 1, 1, tzinfo=UTC), usegmt=True)
_FUTURE_HTTP_DATE = format_datetime(datetime(2099, 1, 1, tzinfo=UTC), usegmt=True)
_STATIC_RATE_HINT = "Wait a minute before retrying, and avoid polling faster than every 10s."
_RETRYABLE_STATUSES = (408, 429, 502, 503, 504)
_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class ZeroJitter(random.Random):
    """Jitter source that contributes nothing, so backoff is exactly the unjittered curve."""

    def uniform(self, a: float, b: float) -> float:
        del a, b
        return 0.0


class HugeJitter(random.Random):
    """Jitter large enough that the 10s ceiling binds on the local delay path."""

    def uniform(self, a: float, b: float) -> float:
        del a, b
        return 100.0


class IsolatedConfig:
    """Temp native/legacy roots so resolution cannot see the developer's real profile."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="vidbyte-cli-core-"))
        self.paths = VidbytePaths(
            config_root=self.root / "config",
            cache_root=self.root / "cache",
            state_root=self.root / "state",
            data_root=self.root / "data",
            legacy_root=self.root / "legacy",
        )
        self.store = ConfigStore(self.paths)

    def resolver(self, environment: Mapping[str, str] | None = None) -> ConfigResolver:
        return ConfigResolver(self.store, dict(environment or {}))

    def seed(self, document: ConfigDocument) -> None:
        self.store.save(document, expected_digest=None)

    def write_legacy(self, document: ConfigDocument) -> None:
        path = self.paths.legacy_config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _response(status: int, headers: Mapping[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        headers=dict(headers or {}),
        request=httpx.Request("GET", "http://127.0.0.1/x"),
    )


def _work_profile() -> ProfileConfig:
    return ProfileConfig(
        api_url="https://work.example.com",
        output_format=OutputFormat.JSON,
        color=ColorMode.NEVER,
        request_timeout_seconds=15.0,
    )


def _default_profile() -> ProfileConfig:
    return ProfileConfig(
        api_url="https://default.example.com",
        output_format=OutputFormat.JSONL,
        color=ColorMode.ALWAYS,
        request_timeout_seconds=45.0,
    )


class RetryPolicyTests(unittest.TestCase):
    """Pins RetryPolicy.decide: what may repeat, and how long to wait first."""

    def _decide(
        self,
        method: str = "GET",
        *,
        keyed: bool = False,
        attempt: int = 1,
        outcome: httpx.Response | httpx.HTTPError | None = None,
        source: random.Random | None = None,
    ) -> object:
        policy = RetryPolicy(random_source=source or random.Random(0))
        return policy.decide(
            RequestMetadata(method, keyed),
            attempt,
            outcome if outcome is not None else _response(503),
        )

    def test_attempt_limit_blocks_even_when_transient(self) -> None:
        for attempt, status in ((3, 503), (4, 503), (3, 429)):
            with self.subTest(attempt=attempt, status=status):
                decision = self._decide(attempt=attempt, outcome=_response(status))
                self.assertFalse(decision.retry)
                self.assertEqual(decision.delay_seconds, 0.0)

    def test_safe_methods_retry_retryable_statuses(self) -> None:
        for method in _SAFE_METHODS:
            for status in _RETRYABLE_STATUSES:
                with self.subTest(method=method, status=status):
                    self.assertTrue(self._decide(method, outcome=_response(status)).retry)

    def test_non_retryable_statuses_never_retry(self) -> None:
        for status in (200, 302, 400, 401, 403, 404, 409, 418, 422, 500, 501, 505):
            with self.subTest(status=status):
                self.assertFalse(self._decide(outcome=_response(status)).retry)

    def test_post_without_idempotency_key_never_retries(self) -> None:
        for outcome in (_response(503), _response(429), httpx.ConnectError("offline")):
            with self.subTest(outcome=type(outcome).__name__):
                self.assertFalse(self._decide("POST", keyed=False, outcome=outcome).retry)

    def test_post_with_idempotency_key_retries_only_when_transient(self) -> None:
        self.assertTrue(self._decide("POST", keyed=True, outcome=_response(503)).retry)
        self.assertFalse(self._decide("POST", keyed=True, outcome=_response(401)).retry)

    def test_unsafe_methods_never_retry(self) -> None:
        for method in ("PUT", "PATCH", "DELETE", "TRACE", "CONNECT", "", "GET "):
            with self.subTest(method=repr(method)):
                self.assertFalse(self._decide(method, outcome=_response(503)).retry)

    def test_method_case_is_normalized(self) -> None:
        self.assertTrue(self._decide("get", outcome=_response(503)).retry)
        self.assertTrue(self._decide("Get", outcome=_response(503)).retry)
        self.assertTrue(self._decide("pOsT", keyed=True, outcome=_response(503)).retry)

    def test_retryable_transport_errors(self) -> None:
        errors: tuple[httpx.HTTPError, ...] = (
            httpx.ConnectError("offline"),
            httpx.ConnectTimeout("offline"),
            httpx.ReadTimeout("offline"),
            httpx.RemoteProtocolError("offline"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.assertTrue(self._decide(outcome=error).retry)

    def test_non_retryable_transport_errors(self) -> None:
        errors: tuple[httpx.HTTPError, ...] = (
            httpx.WriteTimeout("offline"),
            httpx.PoolTimeout("offline"),
            httpx.TimeoutException("offline"),
            httpx.ProtocolError("offline"),
            httpx.ProxyError("offline"),
            httpx.UnsupportedProtocol("offline"),
            httpx.DecodingError("offline"),
            httpx.TooManyRedirects("offline"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.assertFalse(self._decide(outcome=error).retry)

    def test_local_backoff_matches_seeded_jitter(self) -> None:
        jitter = random.Random(0).uniform(0.0, 0.25)
        first = self._decide(attempt=1, outcome=_response(503), source=random.Random(0))
        second = self._decide(attempt=2, outcome=_response(503), source=random.Random(0))
        self.assertTrue(first.retry)
        self.assertFalse(first.delay_clamped)
        self.assertAlmostEqual(first.delay_seconds, 0.25 + jitter)
        self.assertTrue(second.retry)
        self.assertFalse(second.delay_clamped)
        self.assertAlmostEqual(second.delay_seconds, 0.50 + jitter)

    def test_zero_jitter_is_exactly_the_unjittered_curve(self) -> None:
        decision = self._decide(outcome=_response(503), source=ZeroJitter())
        self.assertEqual(decision.delay_seconds, 0.25)
        self.assertFalse(decision.delay_clamped)

    def test_huge_local_jitter_caps_without_setting_clamped(self) -> None:
        # The local path applies the 10s ceiling but never sets delay_clamped; that flag is
        # reserved for a server Retry-After that exceeded the ceiling.
        decision = self._decide(outcome=_response(503), source=HugeJitter())
        self.assertTrue(decision.retry)
        self.assertEqual(decision.delay_seconds, 10.0)
        self.assertFalse(decision.delay_clamped)

    def test_numeric_retry_after_forms(self) -> None:
        cases = (
            ("5", 5.0, False),
            ("10", 10.0, False),
            ("10.0001", 10.0, True),
            ("100", 10.0, True),
            ("0", 0.0, False),
            ("-1", 0.0, False),
            ("+5", 5.0, False),
            ("2.5", 2.5, False),
            ("1e2", 10.0, True),
            ("inf", 10.0, True),
            ("5 ", 5.0, False),
        )
        for header, delay, clamped in cases:
            with self.subTest(header=header):
                decision = self._decide(outcome=_response(429, {"Retry-After": header}))
                self.assertTrue(decision.retry)
                self.assertEqual(decision.delay_seconds, delay)
                self.assertEqual(decision.delay_clamped, clamped)

    def test_nan_retry_after_becomes_a_zero_wait(self) -> None:
        # float("nan") succeeds, then max(0.0, nan) returns 0.0 because the 0.0 is first and
        # NaN comparisons are false. The delay is therefore finite; do not "fix" this into a
        # local-backoff fallback without a dedicated contract change.
        decision = self._decide(outcome=_response(429, {"Retry-After": "nan"}))
        self.assertTrue(decision.retry)
        self.assertEqual(decision.delay_seconds, 0.0)
        self.assertFalse(decision.delay_clamped)

    def test_http_date_retry_after(self) -> None:
        past = self._decide(outcome=_response(429, {"Retry-After": _PAST_HTTP_DATE}))
        self.assertTrue(past.retry)
        self.assertEqual(past.delay_seconds, 0.0)
        self.assertFalse(past.delay_clamped)
        future = self._decide(outcome=_response(429, {"Retry-After": _FUTURE_HTTP_DATE}))
        self.assertTrue(future.retry)
        self.assertEqual(future.delay_seconds, 10.0)
        self.assertTrue(future.delay_clamped)

    def test_unparseable_retry_after_falls_back_to_local_backoff(self) -> None:
        jitter = random.Random(0).uniform(0.0, 0.25)
        for header in (None, "", "not-a-date"):
            headers = {} if header is None else {"Retry-After": header}
            with self.subTest(header=header):
                decision = self._decide(outcome=_response(429, headers), source=random.Random(0))
                self.assertTrue(decision.retry)
                self.assertAlmostEqual(decision.delay_seconds, 0.25 + jitter)
                self.assertFalse(decision.delay_clamped)

    def test_transport_error_uses_local_backoff(self) -> None:
        jitter = random.Random(0).uniform(0.0, 0.25)
        decision = self._decide(outcome=httpx.ConnectError("offline"), source=random.Random(0))
        self.assertTrue(decision.retry)
        self.assertAlmostEqual(decision.delay_seconds, 0.25 + jitter)


class ApiProblemMapperTests(unittest.TestCase):
    """Pins status→failure classification and the mapper's digit-only Retry-After parser."""

    def setUp(self) -> None:
        self.mapper = ApiProblemMapper()

    def test_status_table(self) -> None:
        cases: tuple[tuple[int, type, CliErrorCode, ExitCode, bool], ...] = (
            (
                401,
                ApiCredentialsRejected,
                CliErrorCode.AUTH_REQUIRED,
                ExitCode.AUTHENTICATION,
                False,
            ),
            (403, ApiPermissionDenied, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION, False),
            (
                402,
                ApiCreditExhausted,
                CliErrorCode.CREDIT_EXHAUSTED,
                ExitCode.CREDIT_EXHAUSTED,
                False,
            ),
            (409, ApiRequestConflicted, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE, False),
            (400, ApiRequestRejected, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE, False),
            (422, ApiRequestRejected, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE, False),
            (429, ApiRateLimited, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE, True),
            (500, ApiUnavailable, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE, True),
            (
                418,
                ApiOperationFailed,
                CliErrorCode.OPERATION_FAILED,
                ExitCode.OPERATIONAL_FAILURE,
                False,
            ),
        )
        for status, cls, code, exit_code, retryable in cases:
            with self.subTest(status=status):
                error = self.mapper.from_response(_response(status))
                self.assertIsInstance(error, cls)
                self.assertIs(error.code, code)
                self.assertEqual(error.exit_code, int(exit_code))
                self.assertEqual(error.retryable, retryable)

    def test_unavailable_family_and_unclassified_statuses(self) -> None:
        for status in (501, 502, 503, 504, 599):
            with self.subTest(status=status):
                error = self.mapper.from_response(_response(status))
                self.assertIsInstance(error, ApiUnavailable)
        for status in (200, 204, 301, 302, 307, 308, 499):
            with self.subTest(status=status):
                error = self.mapper.from_response(_response(status))
                self.assertIsInstance(error, ApiOperationFailed)

    def test_404_forks_on_route_not_found(self) -> None:
        missing = self.mapper.from_response(_response(404), route_not_found=False)
        self.assertIsInstance(missing, ApiResourceNotFound)
        self.assertIs(missing.code, CliErrorCode.OPERATION_FAILED)
        route = self.mapper.from_response(_response(404), route_not_found=True)
        self.assertIsInstance(route, ApiRouteMissing)
        self.assertIs(route.code, CliErrorCode.API_UNAVAILABLE)

    def test_route_not_found_flag_is_ignored_off_404(self) -> None:
        error = self.mapper.from_response(_response(401), route_not_found=True)
        self.assertIsInstance(error, ApiCredentialsRejected)

    def test_request_id_bounds(self) -> None:
        self.assertEqual(
            self.mapper.from_response(_response(401, {"x-request-id": "req_abc"})).request_id,
            "req_abc",
        )
        self.assertIsNone(self.mapper.from_response(_response(401)).request_id)
        self.assertIsNone(
            self.mapper.from_response(_response(401, {"x-request-id": ""})).request_id
        )
        self.assertEqual(
            self.mapper.from_response(_response(401, {"x-request-id": "x"})).request_id, "x"
        )
        kept = "k" * 128
        self.assertEqual(
            self.mapper.from_response(_response(401, {"x-request-id": kept})).request_id, kept
        )
        self.assertIsNone(
            self.mapper.from_response(_response(401, {"x-request-id": "k" * 129})).request_id
        )

    def test_rate_limit_retry_after_is_digit_only(self) -> None:
        hinted = self.mapper.from_response(_response(429, {"Retry-After": "42"}))
        self.assertIsInstance(hinted, ApiRateLimited)
        self.assertIn("42", hinted.hint or "")
        padded = self.mapper.from_response(_response(429, {"Retry-After": "042"}))
        self.assertIn("42", padded.hint or "")
        spaced = self.mapper.from_response(_response(429, {"Retry-After": " 42 "}))
        self.assertIn("42", spaced.hint or "")
        for header in (_FUTURE_HTTP_DATE, "5.5", "-1", "+42", "", None):
            headers = {} if header is None else {"Retry-After": header}
            with self.subTest(header=header):
                error = self.mapper.from_response(_response(429, headers))
                self.assertEqual(error.hint, _STATIC_RATE_HINT)

    def test_rate_limit_request_id_and_retry_after_are_independent(self) -> None:
        error = self.mapper.from_response(
            _response(429, {"Retry-After": "7", "x-request-id": "req_429"})
        )
        self.assertEqual(error.request_id, "req_429")
        self.assertIn("7", error.hint or "")

    def test_response_body_is_never_copied_into_the_failure(self) -> None:
        error = self.mapper.from_response(
            httpx.Response(
                401,
                headers={"content-type": "application/json"},
                content=b'{"detail":"%s"}' % _SECRET.encode(),
                request=httpx.Request("GET", "http://127.0.0.1/x"),
            )
        )
        rendered = " ".join(
            part for part in (error.message, error.description, error.trace, error.hint) if part
        )
        self.assertNotIn(_SECRET, rendered)

    def test_from_transport_is_unreachable_for_every_http_error(self) -> None:
        for error in (httpx.ConnectError("offline"), httpx.ReadTimeout("offline")):
            with self.subTest(error=type(error).__name__):
                failure = self.mapper.from_transport(error)
                self.assertIsInstance(failure, ApiUnreachable)
                self.assertIs(failure.code, CliErrorCode.API_UNAVAILABLE)
                self.assertTrue(failure.retryable)


class ConfigResolverTests(unittest.TestCase):
    """Pins five-layer precedence, provenance, validation, and read-only resolution."""

    def setUp(self) -> None:
        self.isolated = IsolatedConfig()

    def tearDown(self) -> None:
        self.isolated.cleanup()

    def test_built_in_defaults_when_nothing_is_stored(self) -> None:
        resolved = self.isolated.resolver().resolve()
        self.assertEqual(resolved.profile, "default")
        self.assertEqual(resolved.api_url, DEFAULT_API_URL)
        self.assertEqual(resolved.output_format, OutputFormat.HUMAN)
        self.assertEqual(resolved.color, ColorMode.AUTO)
        self.assertEqual(resolved.request_timeout_seconds, 30.0)
        self.assertIsNone(resolved.config_path)
        self.assertEqual(set(resolved.provenance), set(ConfigField))
        self.assertTrue(
            all(source is ConfigSource.BUILT_IN for source in resolved.provenance.values())
        )

    def test_empty_resolve_forms_are_identical(self) -> None:
        resolver = self.isolated.resolver()
        self.assertEqual(resolver.resolve(), resolver.resolve(None))
        self.assertEqual(resolver.resolve(), resolver.resolve(ConfigOverrides()))

    def test_command_overrides_win_every_field(self) -> None:
        resolved = self.isolated.resolver().resolve(
            ConfigOverrides(
                profile="work",
                api_url="https://command.example.com",
                output_format=OutputFormat.JSON,
                color=ColorMode.NEVER,
                request_timeout_seconds=12.0,
            )
        )
        self.assertEqual(resolved.profile, "work")
        self.assertEqual(resolved.api_url, "https://command.example.com")
        self.assertEqual(resolved.output_format, OutputFormat.JSON)
        self.assertEqual(resolved.color, ColorMode.NEVER)
        self.assertEqual(resolved.request_timeout_seconds, 12.0)
        self.assertTrue(
            all(source is ConfigSource.COMMAND for source in resolved.provenance.values())
        )

    def test_environment_beats_stored_profiles(self) -> None:
        self.isolated.seed(
            ConfigDocument(
                active_profile="default",
                profiles={"default": _default_profile(), "work": _work_profile()},
            )
        )
        resolved = self.isolated.resolver(
            {
                "VIDBYTE_PROFILE": "work",
                "VIDBYTE_API_URL": "https://env.example.com",
                "VIDBYTE_OUTPUT_FORMAT": "none",
                "VIDBYTE_COLOR": "auto",
                "VIDBYTE_REQUEST_TIMEOUT_SECONDS": "80",
            }
        ).resolve()
        self.assertEqual(resolved.profile, "work")
        self.assertEqual(resolved.api_url, "https://env.example.com")
        self.assertEqual(resolved.output_format, OutputFormat.NONE)
        self.assertEqual(resolved.color, ColorMode.AUTO)
        self.assertEqual(resolved.request_timeout_seconds, 80.0)
        self.assertTrue(
            all(source is ConfigSource.ENVIRONMENT for source in resolved.provenance.values())
        )

    def test_selected_profile_beats_default_profile(self) -> None:
        self.isolated.seed(
            ConfigDocument(
                active_profile="work",
                profiles={"default": _default_profile(), "work": _work_profile()},
            )
        )
        resolved = self.isolated.resolver().resolve()
        self.assertEqual(resolved.profile, "work")
        self.assertEqual(resolved.api_url, "https://work.example.com")
        self.assertEqual(resolved.output_format, OutputFormat.JSON)
        self.assertTrue(
            all(source is ConfigSource.SELECTED_PROFILE for source in resolved.provenance.values())
        )
        self.assertEqual(Path(resolved.config_path or ""), self.isolated.paths.config_file())

    def test_profile_selection_order(self) -> None:
        self.isolated.seed(
            ConfigDocument(
                active_profile="default",
                profiles={"default": _default_profile(), "work": _work_profile()},
            )
        )
        command = self.isolated.resolver({"VIDBYTE_PROFILE": "default"}).resolve(
            ConfigOverrides(profile="work")
        )
        self.assertEqual(command.profile, "work")
        env = self.isolated.resolver({"VIDBYTE_PROFILE": "work"}).resolve()
        self.assertEqual(env.profile, "work")

    def test_missing_selected_profile_falls_back_to_default_profile(self) -> None:
        self.isolated.seed(ConfigDocument(profiles={"default": _default_profile()}))
        resolved = self.isolated.resolver().resolve(ConfigOverrides(profile="ghost"))
        self.assertEqual(resolved.profile, "ghost")
        self.assertEqual(resolved.api_url, "https://default.example.com")
        self.assertTrue(
            all(source is ConfigSource.DEFAULT_PROFILE for source in resolved.provenance.values())
        )

    def test_file_without_default_or_selected_profile_is_built_in(self) -> None:
        self.isolated.seed(
            ConfigDocument(active_profile="work", profiles={"work": _work_profile()})
        )
        resolved = self.isolated.resolver().resolve(ConfigOverrides(profile="ghost"))
        self.assertEqual(resolved.profile, "ghost")
        self.assertEqual(resolved.api_url, DEFAULT_API_URL)
        self.assertTrue(
            all(source is ConfigSource.BUILT_IN for source in resolved.provenance.values())
        )
        self.assertEqual(Path(resolved.config_path or ""), self.isolated.paths.config_file())

    def test_mixed_layer_provenance(self) -> None:
        self.isolated.seed(
            ConfigDocument(active_profile="work", profiles={"work": _work_profile()})
        )
        resolved = self.isolated.resolver({"VIDBYTE_COLOR": "always"}).resolve(
            ConfigOverrides(output_format=OutputFormat.JSONL)
        )
        self.assertEqual(resolved.output_format, OutputFormat.JSONL)
        self.assertEqual(resolved.provenance[ConfigField.OUTPUT_FORMAT], ConfigSource.COMMAND)
        self.assertEqual(resolved.color, ColorMode.ALWAYS)
        self.assertEqual(resolved.provenance[ConfigField.COLOR], ConfigSource.ENVIRONMENT)
        self.assertEqual(resolved.request_timeout_seconds, 15.0)
        self.assertEqual(
            resolved.provenance[ConfigField.REQUEST_TIMEOUT_SECONDS], ConfigSource.SELECTED_PROFILE
        )
        self.assertEqual(resolved.api_url, "https://work.example.com")
        self.assertEqual(resolved.provenance[ConfigField.API_URL], ConfigSource.SELECTED_PROFILE)

    def test_empty_field_env_is_unset_but_whitespace_profile_is_invalid(self) -> None:
        resolved = self.isolated.resolver({"VIDBYTE_API_URL": "", "VIDBYTE_COLOR": "   "}).resolve()
        self.assertEqual(resolved.api_url, DEFAULT_API_URL)
        self.assertEqual(resolved.provenance[ConfigField.API_URL], ConfigSource.BUILT_IN)
        self.assertEqual(resolved.color, ColorMode.AUTO)
        empty_profile = self.isolated.resolver({"VIDBYTE_PROFILE": ""}).resolve()
        self.assertEqual(empty_profile.profile, "default")
        with self.assertRaises(InvalidConfigOverride):
            self.isolated.resolver({"VIDBYTE_PROFILE": "  "}).resolve()
        with self.assertRaises(InvalidConfigOverride):
            self.isolated.resolver({"VIDBYTE_PROFILE": "has space"}).resolve()

    def test_invalid_origins_and_enums_raise_without_echoing_the_value(self) -> None:
        bad_env = (
            {"VIDBYTE_API_URL": "not-a-url"},
            {"VIDBYTE_API_URL": "http://example.com"},
            {"VIDBYTE_API_URL": "https://example.com/v1"},
            {"VIDBYTE_API_URL": "https://user:pass@example.com"},
            {"VIDBYTE_API_URL": "https://example.com?q=1"},
            {"VIDBYTE_API_URL": "https://example.com#frag"},
            {"VIDBYTE_OUTPUT_FORMAT": "JSON"},
            {"VIDBYTE_COLOR": "Always"},
            {"VIDBYTE_REQUEST_TIMEOUT_SECONDS": "abc"},
            {"VIDBYTE_REQUEST_TIMEOUT_SECONDS": "0.5"},
            {"VIDBYTE_REQUEST_TIMEOUT_SECONDS": "301"},
        )
        for environment in bad_env:
            with self.subTest(environment=environment):
                with self.assertRaises(InvalidConfigOverride) as raised:
                    self.isolated.resolver(environment).resolve()
                error = raised.exception
                self.assertIs(error.code, CliErrorCode.CONFIG_INVALID)
                rendered = " ".join(
                    part
                    for part in (error.message, error.description, error.trace, error.hint)
                    if part
                )
                for value in environment.values():
                    self.assertNotIn(value, rendered)

    def test_loopback_http_and_https_origins(self) -> None:
        cases = (
            ("http://127.0.0.1", "http://127.0.0.1"),
            ("http://localhost", "http://localhost"),
            ("http://[::1]", "http://[::1]"),
            ("https://host:8443", "https://host:8443"),
            ("https://host/", "https://host"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                resolved = self.isolated.resolver({"VIDBYTE_API_URL": raw}).resolve()
                self.assertEqual(resolved.api_url, expected)

    def test_enum_and_timeout_bounds(self) -> None:
        for value, expected in (
            ("json", OutputFormat.JSON),
            ("jsonl", OutputFormat.JSONL),
            ("none", OutputFormat.NONE),
            ("human", OutputFormat.HUMAN),
        ):
            with self.subTest(format=value):
                resolved = self.isolated.resolver({"VIDBYTE_OUTPUT_FORMAT": value}).resolve()
                self.assertEqual(resolved.output_format, expected)
        for value, expected in (
            ("always", ColorMode.ALWAYS),
            ("auto", ColorMode.AUTO),
            ("never", ColorMode.NEVER),
        ):
            with self.subTest(color=value):
                resolved = self.isolated.resolver({"VIDBYTE_COLOR": value}).resolve()
                self.assertEqual(resolved.color, expected)
        for raw, expected in (("1", 1.0), ("300", 300.0), ("30.5", 30.5)):
            with self.subTest(timeout=raw):
                resolved = self.isolated.resolver(
                    {"VIDBYTE_REQUEST_TIMEOUT_SECONDS": raw}
                ).resolve()
                self.assertEqual(resolved.request_timeout_seconds, expected)

    def test_empty_command_api_url_keeps_command_provenance(self) -> None:
        resolved = self.isolated.resolver().resolve(ConfigOverrides(api_url=""))
        self.assertEqual(resolved.api_url, DEFAULT_API_URL)
        self.assertEqual(resolved.provenance[ConfigField.API_URL], ConfigSource.COMMAND)

    def test_resolve_does_not_create_a_config_file(self) -> None:
        self.isolated.resolver().resolve()
        self.assertFalse(self.isolated.paths.config_file().exists())

    def test_native_file_beats_legacy_file(self) -> None:
        self.isolated.write_legacy(ConfigDocument(profiles={"default": _default_profile()}))
        self.isolated.seed(ConfigDocument(profiles={"default": _work_profile()}))
        resolved = self.isolated.resolver().resolve()
        self.assertEqual(resolved.api_url, "https://work.example.com")
        self.assertEqual(Path(resolved.config_path or ""), self.isolated.paths.config_file())

    def test_legacy_file_is_used_when_native_is_absent(self) -> None:
        self.isolated.write_legacy(ConfigDocument(profiles={"default": _work_profile()}))
        resolved = self.isolated.resolver().resolve()
        self.assertEqual(resolved.api_url, "https://work.example.com")
        self.assertEqual(Path(resolved.config_path or ""), self.isolated.paths.legacy_config_file())

    def test_whitespace_around_env_values_is_stripped(self) -> None:
        resolved = self.isolated.resolver(
            {
                "VIDBYTE_OUTPUT_FORMAT": " json ",
                "VIDBYTE_COLOR": " never ",
                "VIDBYTE_REQUEST_TIMEOUT_SECONDS": " 45 ",
            }
        ).resolve()
        self.assertEqual(resolved.output_format, OutputFormat.JSON)
        self.assertEqual(resolved.color, ColorMode.NEVER)
        self.assertEqual(resolved.request_timeout_seconds, 45.0)

    def test_env_timeout_overrides_only_that_field(self) -> None:
        self.isolated.seed(
            ConfigDocument(active_profile="work", profiles={"work": _work_profile()})
        )
        resolved = self.isolated.resolver({"VIDBYTE_REQUEST_TIMEOUT_SECONDS": "90"}).resolve()
        self.assertEqual(resolved.request_timeout_seconds, 90.0)
        self.assertEqual(
            resolved.provenance[ConfigField.REQUEST_TIMEOUT_SECONDS], ConfigSource.ENVIRONMENT
        )
        self.assertEqual(resolved.provenance[ConfigField.API_URL], ConfigSource.SELECTED_PROFILE)
        self.assertEqual(
            resolved.provenance[ConfigField.OUTPUT_FORMAT], ConfigSource.SELECTED_PROFILE
        )


def main() -> int:
    program = unittest.main(verbosity=2, exit=False)
    result = program.result
    if result.testsRun == 0 or not result.wasSuccessful():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
