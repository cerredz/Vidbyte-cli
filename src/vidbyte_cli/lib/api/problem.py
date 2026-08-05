"""FILE: src/vidbyte_cli/lib/api/problem.py

PURPOSE: Maps HTTP failures to stable user-safe CLI errors without parsing backend prose.

ROLE IN CODEBASE: ApiClient invokes ApiProblemMapper only after retry policy is exhausted.
Request IDs are retained; response bodies and provider exception strings are not.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import httpx

from ..errors import CliError, CliErrorCode, ExitCode


class ApiProblemMapper:
    """Status-driven safe error classification."""

    def from_response(self, response: httpx.Response) -> CliError:
        request_id = self._request_id(response)
        status = response.status_code
        if status in {401, 403}:
            return CliError(
                CliErrorCode.AUTH_REQUIRED,
                "The Vidbyte API rejected the current credentials.",
                ExitCode.AUTHENTICATION,
                hint="Run 'vidbyte-cli login' for the selected profile.",
                request_id=request_id,
            )
        if status == 402:
            return CliError(
                CliErrorCode.CREDIT_EXHAUSTED,
                "The Vidbyte account does not have enough credits for this operation.",
                ExitCode.CREDIT_EXHAUSTED,
                request_id=request_id,
            )
        if status in {400, 409, 422}:
            return CliError(
                CliErrorCode.INVALID_ARGUMENT,
                "The Vidbyte API rejected the request.",
                ExitCode.USAGE,
                hint="Review the command inputs and retry.",
                request_id=request_id,
            )
        if status == 404:
            return CliError(
                CliErrorCode.OPERATION_FAILED,
                "The requested Vidbyte resource was not found.",
                request_id=request_id,
            )
        if status == 429 or status >= 500:
            return CliError(
                CliErrorCode.API_UNAVAILABLE,
                "The Vidbyte API is temporarily unavailable.",
                hint="Retry the command after a short delay.",
                retryable=True,
                request_id=request_id,
            )
        return CliError(
            CliErrorCode.OPERATION_FAILED,
            "The Vidbyte API could not complete the operation.",
            request_id=request_id,
        )

    def from_transport(self, error: httpx.HTTPError) -> CliError:
        return CliError(
            CliErrorCode.API_UNAVAILABLE,
            "The Vidbyte API could not be reached.",
            hint="Check connectivity and the configured API URL, then retry.",
            retryable=True,
            cause=error,
        )

    def _request_id(self, response: httpx.Response) -> str | None:
        value = response.headers.get("x-request-id")
        if value is None or not 1 <= len(value) <= 128:
            return None
        return str(value)
