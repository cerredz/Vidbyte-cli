"""One HTTP failure status in, one typed CliError out.

Classification reads the status code and the `x-request-id` header, and nothing else. The
response body is never parsed: failure prose in this CLI is static authored text, and a
backend body may quote a prompt, a credential, or another account's content.

The arms are split more finely than the status families suggest, because the remedies
differ. 401 means log in, 403 means grant a scope, 429 means poll less often, and a 409 on
this surface always means the same thing about continuing a run.
"""

from __future__ import annotations

import httpx

from ..errors.cli_error import CliError
from ..errors.failures import (
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
)
from .response import ResponseDecoder


class ApiProblemMapper:
    """Status-driven, body-free classification of backend failures."""

    def from_response(
        self,
        response: httpx.Response,
        *,
        route_not_found: bool = False,
    ) -> CliError:
        # Maps one non-success status onto the failure whose hint actually resolves it.
        request_id = ResponseDecoder.request_id(response)
        status = response.status_code
        match status:
            case 401:
                return ApiCredentialsRejected(request_id)
            case 403:
                return ApiPermissionDenied(request_id)
            case 402:
                return ApiCreditExhausted(request_id)
            case 404:
                if route_not_found:
                    return ApiRouteMissing(request_id)
                return ApiResourceNotFound(request_id)
            case 409:
                return ApiRequestConflicted(request_id)
            case 400 | 422:
                return ApiRequestRejected(request_id)
            case 429:
                return ApiRateLimited(request_id, self._retry_after(response))
            case _ if status >= 500:
                return ApiUnavailable(request_id)
            case _:
                return ApiOperationFailed(request_id)

    def from_transport(self, error: httpx.HTTPError) -> CliError:
        # No response ever arrived, so there is no status and no request ID to report.
        return ApiUnreachable(error)

    def _retry_after(self, response: httpx.Response) -> int | None:
        # The authored rate-limit hint may repeat only a bounded numeric delta.
        value = response.headers.get("retry-after", "").strip()
        return int(value) if value.isdigit() else None
