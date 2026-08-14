"""Typed HTTP client for the Vidbyte public API.

Owns the base URL, API-key header injection, bounded response decoding, and status-driven
failure classification. Commands and harnesses never call httpx directly — all HTTP goes
through a typed endpoint group built on this client.

Settings and the credential arrive already resolved, so this client never reads the
environment: doing so would let a stale variable outrank an explicit option and would skip
the origin validation that `ResolvedConfig.api_url` has already passed.

Classification is by HTTP status only. The backend serves several different error-body
shapes, so no single `code` field is a platform contract, and a generic client that knew one
route's spelling would be wrong for the next one.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

from ..auth.credentials import Credentials
from ..config import ResolvedConfig
from ..errors.cli_error import CliError
from ..errors.failures import (
    ApiCredentialRejected,
    ApiOperationFailed,
    ApiProtocolError,
    ApiRequestPathInvalid,
    ApiRequestRejected,
    ApiRouteMissing,
    ApiTemporarilyUnavailable,
    ApiUnreachable,
    NotImplementedFeature,
)

if TYPE_CHECKING:
    import httpx

# The backend reads this header first and accepts `Authorization: Bearer` only as a fallback,
# so the key travels here and nowhere else. Sending both would be worse than sending one: the
# gatekeeper stops at a malformed `x-api-key` instead of falling through to the bearer value.
API_KEY_HEADER_NAME = "x-api-key"
_JSON_MEDIA_TYPE = "application/json"
# Bounds a hostile or misrouted response before it is parsed into memory. Generous for the
# small objects these routes return, and small enough that a proxy dumping a page is refused.
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_REQUEST_ID_CHARACTERS = 128

TModel = TypeVar("TModel", bound=BaseModel)


class ApiClient:
    def __init__(self, config: ResolvedConfig, credentials: Credentials) -> None:
        # Takes the invocation's resolved host, timeout, and secret; resolves nothing itself.
        self.base_url = config.api_url
        self.timeout_seconds = config.request_timeout_seconds
        # The key is a secret: it is held here only to set the auth header, never logged.
        self._credentials = credentials

    def auth_headers(self) -> dict[str, str]:
        # The single point where the stored secret is unwrapped for transmission.
        return {API_KEY_HEADER_NAME: self._credentials.secret_value()}

    def post_direct(self, path: str, model: type[TModel]) -> TModel:
        # POSTs with no body and validates the response object itself, not an envelope's `data`.
        response = self._send(self._url(path))
        if not 200 <= response.status_code < 300:
            raise self._failure_for_status(response)
        return self._decode(response, model)

    def get(self, path: str, model: type[TModel]) -> TModel:
        # Performs an authenticated GET, unwraps the envelope, validates into `model`.
        raise NotImplementedFeature("api client requests")

    def get_list(self, path: str, model: type[TModel]) -> list[TModel]:
        # GET returning a list payload, each item validated into `model`.
        raise NotImplementedFeature("api client requests")

    def post(self, path: str, body: BaseModel, model: type[TModel]) -> TModel:
        # Performs an authenticated POST, unwraps the envelope, validates into `model`.
        raise NotImplementedFeature("api client requests")

    def _url(self, path: str) -> str:
        # Joins a relative path onto the configured origin, refusing anything that could
        # retarget the request and carry the API key to a host the caller never named.
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ApiRequestPathInvalid()
        # ApiOrigin.parse already guarantees the base URL has no path, query, or fragment.
        return f"{self.base_url}{path}"

    def _send(self, url: str) -> httpx.Response:
        # Executes the POST with the invocation timeout and redirects deliberately disabled.
        import httpx  # Imported here because module scope would add ~0.14s to every --help.

        headers = {**self.auth_headers(), "Accept": _JSON_MEDIA_TYPE}
        try:
            # follow_redirects is httpx's default but is stated explicitly: following one would
            # replay the API key to whatever host the redirect names.
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                return client.post(url, headers=headers)
        except httpx.HTTPError as error:
            raise ApiUnreachable(error) from error

    def _decode(self, response: httpx.Response, model: type[TModel]) -> TModel:
        # Media type, size, JSON validity, and schema are all checked before typed data
        # crosses the transport boundary.
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != _JSON_MEDIA_TYPE and not media_type.endswith("+json"):
            raise ApiProtocolError()
        content = response.content
        if not content or len(content) > _MAX_RESPONSE_BYTES:
            raise ApiProtocolError()
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiProtocolError(error) from error
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise ApiProtocolError(error) from error

    def _failure_for_status(self, response: httpx.Response) -> CliError:
        # One switch over the status so every outcome the CLI understands reads in one place.
        request_id = self._request_id(response)
        match response.status_code:
            case 401 | 403:
                return ApiCredentialRejected(request_id)
            case 400 | 409 | 422:
                return ApiRequestRejected(request_id)
            case 404:
                return ApiRouteMissing(request_id)
            case 429:
                return ApiTemporarilyUnavailable(request_id, self._retry_after(response))
            case status if 500 <= status < 600:
                return ApiTemporarilyUnavailable(request_id)
            case _:
                return ApiOperationFailed(request_id)

    def _request_id(self, response: httpx.Response) -> str | None:
        # A correlation id is the one piece of a failed response safe to keep and repeat.
        value = str(response.headers.get("x-request-id", ""))
        if not 1 <= len(value) <= _MAX_REQUEST_ID_CHARACTERS:
            return None
        return value

    def _retry_after(self, response: httpx.Response) -> int | None:
        # Only the delta-seconds form is honoured; an HTTP-date is ignored rather than guessed.
        value = response.headers.get("retry-after", "").strip()
        return int(value) if value.isdigit() else None
