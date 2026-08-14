"""What a backend route's success body looks like, and the only decoder that reads one.

Routes disagree about their envelope: the research surface returns its DTO directly, while
the older public resources wrap it in `{success, data}`. The shape is therefore declared per
route by the endpoint group rather than assumed here, so adding a route cannot silently
unwrap something that was never wrapped.

Every rejection is the same failure on purpose. A caller cannot act differently on a wrong
content type than on a schema mismatch, and telling them apart would mean quoting the body.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from ..errors.failures import ApiResponseUnsupported

TModel = TypeVar("TModel", bound=BaseModel)
# Bounds a hostile or misrouted response before it is parsed into memory.
_MAX_RESPONSE_BYTES = 5_000_000


class ResponseShape(StrEnum):
    """How a route wraps the payload a caller actually wants."""

    DIRECT = "direct"
    ENVELOPE = "envelope"
    LIST_ENVELOPE = "list_envelope"


class ResponseDecoder:
    """Bounded validation from an HTTP success response into typed models."""

    def one(
        self,
        response: httpx.Response,
        model: type[TModel],
        shape: ResponseShape,
    ) -> TModel:
        # Decodes a single record, unwrapping the envelope only when the route declares one.
        payload = self._payload(response)
        if shape is not ResponseShape.DIRECT:
            payload = self._unwrap(response, payload)
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise self._unsupported(response, error) from error

    def many(self, response: httpx.Response, model: type[TModel]) -> list[TModel]:
        # Decodes an enveloped collection; no route returns a bare top-level JSON array.
        payload = self._unwrap(response, self._payload(response))
        try:
            return TypeAdapter(list[model]).validate_python(payload)  # type: ignore[valid-type]
        except ValidationError as error:
            raise self._unsupported(response, error) from error

    def _payload(self, response: httpx.Response) -> object:
        # Content type and both size bounds are checked before any parsing happens.
        if response.status_code == 204:
            raise self._unsupported(response)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise self._unsupported(response)
        # A chunked response declares no length, so the materialized body is bounded too.
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > _MAX_RESPONSE_BYTES:
            raise self._unsupported(response)
        content = response.content
        if not content or len(content) > _MAX_RESPONSE_BYTES:
            raise self._unsupported(response)
        try:
            return json.loads(content)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise self._unsupported(response, error) from error

    def _unwrap(self, response: httpx.Response, payload: object) -> object:
        # The `{success, data}` wrapper the older public resources return.
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise self._unsupported(response)
        data = payload.get("data")
        if data is None:
            raise self._unsupported(response)
        return data

    def _unsupported(
        self,
        response: httpx.Response,
        cause: Exception | None = None,
    ) -> ApiResponseUnsupported:
        return ApiResponseUnsupported(self.request_id(response), cause)

    @staticmethod
    def request_id(response: httpx.Response) -> str | None:
        # A correlation header, never a body field: only headers are safe to echo back.
        value = response.headers.get("x-request-id")
        if value is None or not 1 <= len(value) <= 128:
            return None
        return str(value)
