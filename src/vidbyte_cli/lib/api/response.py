"""FILE: src/vidbyte_cli/lib/api/response.py

PURPOSE: Defines explicit backend response shapes and a bounded JSON decoder.

ROLE IN CODEBASE: ApiClient delegates successful response validation here so endpoint
adapters state whether a route returns a direct DTO, envelope, or enveloped list.

ARCHITECTURE NOTE: Content type, size, JSON shape, envelope success/data, and Pydantic
validation are all checked before typed data crosses the transport boundary.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from ..errors import CliError, CliErrorCode

TModel = TypeVar("TModel", bound=BaseModel)
_MAX_RESPONSE_BYTES = 5_000_000


class ResponseShape(StrEnum):
    DIRECT = "direct"
    ENVELOPE = "envelope"
    LIST_ENVELOPE = "list_envelope"


class ResponseDecoder:
    """Bounded validation from an HTTP success response to typed DTOs."""

    def one(
        self,
        response: httpx.Response,
        model: type[TModel],
        shape: ResponseShape,
    ) -> TModel:
        payload = self._payload(response)
        if shape is ResponseShape.ENVELOPE:
            payload = self._unwrap(payload)
        elif shape is ResponseShape.LIST_ENVELOPE:
            raise self._protocol_error()
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise self._protocol_error(error) from error

    def many(
        self,
        response: httpx.Response,
        model: type[TModel],
        shape: ResponseShape,
    ) -> list[TModel]:
        payload = self._payload(response)
        if shape is ResponseShape.LIST_ENVELOPE:
            payload = self._unwrap(payload)
        elif shape is ResponseShape.ENVELOPE:
            payload = self._unwrap(payload)
        try:
            return TypeAdapter(list[model]).validate_python(payload)  # type: ignore[valid-type]
        except ValidationError as error:
            raise self._protocol_error(error) from error

    def _payload(self, response: httpx.Response) -> object:
        if response.status_code == 204:
            raise self._protocol_error()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise self._protocol_error()
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > _MAX_RESPONSE_BYTES:
            raise self._protocol_error()
        content = response.content
        if not content or len(content) > _MAX_RESPONSE_BYTES:
            raise self._protocol_error()
        try:
            return json.loads(content)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise self._protocol_error(error) from error

    def _unwrap(self, payload: object) -> object:
        if not isinstance(payload, dict):
            raise self._protocol_error()
        if payload.get("success") is False:
            raise self._protocol_error()
        if "data" not in payload or payload["data"] is None:
            raise self._protocol_error()
        return payload["data"]

    def _protocol_error(self, cause: Exception | None = None) -> CliError:
        return CliError(
            CliErrorCode.API_PROTOCOL_ERROR,
            "The Vidbyte API returned an unsupported response.",
            hint="Retry once, then report the request ID if the problem continues.",
            cause=cause,
        )
