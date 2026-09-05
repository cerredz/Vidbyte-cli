"""Live probe verifiers for provider BYOK keys.

Verifies OpenAI via GET https://api.openai.com/v1/models with Authorization: Bearer,
Claude via GET https://api.anthropic.com/v1/models with x-api-key + anthropic-version,
and Grok/DeepSeek/GLM/Muse via Bearer probes to their native /v1/models endpoints.
"""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ...types.provider import PROVIDER_PROBE_URLS, Provider
from ..errors.failures import (
    ProviderApiProtocolError,
    ProviderApiUnreachable,
    ProviderCredentialsRejected,
    ProviderRateLimited,
    ProviderRequestRejected,
)
from .provider_credentials import ProviderCredentials

_MAX_RESPONSE_BYTES = 1_048_576


class ProviderIdentity(BaseModel):
    """Non-secret identity behind a verified provider key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    verified: bool = True


class ProviderVerifier(Protocol):
    """Proves a candidate provider key against its native endpoint."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity: ...


class _BaseProviderVerifier:
    """Shared transport and decoding for one provider probe."""

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Subclasses define exact auth headers per provider docs.
        raise NotImplementedError

    def _url(self, provider: Provider) -> str:
        # Canonical probe URL per provider.
        return PROVIDER_PROBE_URLS[provider]

    def _probe(self, credentials: ProviderCredentials, timeout_seconds: float) -> None:
        # Executes the live GET and classifies the outcome.
        import httpx

        url = self._url(credentials.provider)
        headers = {"Accept": "application/json", **self._headers(credentials)}
        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
                response = client.get(url, headers=headers)
        except httpx.HTTPError as error:
            raise ProviderApiUnreachable(credentials.provider.value, error) from error
        self._classify_status(credentials, response)
        self._validate_body(credentials, response)

    def _classify_status(self, credentials: ProviderCredentials, response: object) -> None:
        # Maps status to a typed failure before any body is inspected.
        status = int(getattr(response, "status_code", 0))
        headers = getattr(response, "headers", {})
        if status == 429:
            retry = headers.get("Retry-After") if hasattr(headers, "get") else None
            try:
                retry_after = int(retry) if retry is not None else None
            except ValueError:
                retry_after = None
            raise ProviderRateLimited(credentials.provider.value, retry_after)
        if status in (401, 403):
            raise ProviderCredentialsRejected(credentials.provider.value)
        if status in (400, 404, 409, 422):
            raise ProviderRequestRejected(credentials.provider.value)
        if 500 <= status < 600:
            raise ProviderApiUnreachable(credentials.provider.value)
        if not 200 <= status < 300:
            raise ProviderRequestRejected(credentials.provider.value)

    def _validate_body(self, credentials: ProviderCredentials, response: object) -> None:
        # Bounds, parses, and shape-checks the 2xx body.
        content = getattr(response, "content", b"")
        if not content or len(content) > _MAX_RESPONSE_BYTES:
            raise ProviderApiProtocolError(credentials.provider.value)
        try:
            payload = json.loads(content)
        except (ValueError, json.JSONDecodeError) as error:
            raise ProviderApiProtocolError(credentials.provider.value, error) from error
        if not isinstance(payload, dict):
            raise ProviderApiProtocolError(credentials.provider.value)
        # OpenAI-style uses data; Gemini/Cohere use models.
        data = payload.get("data")
        if isinstance(data, list):
            return
        models = payload.get("models")
        if isinstance(models, list):
            return
        raise ProviderApiProtocolError(credentials.provider.value)


class OpenAIVerifier(_BaseProviderVerifier):
    """Proves an OpenAI key via GET /v1/models with Bearer auth."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # Uses a short timeout derived from caller's config where available.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Exact string per OpenAI docs: Authorization: Bearer $OPENAI_API_KEY
        return {"Authorization": f"Bearer {credentials.secret_value()}"}


class ClaudeVerifier(_BaseProviderVerifier):
    """Proves a Claude key via GET /v1/models with x-api-key + version."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # Anthropic requires anthropic-version header on every request.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Per Anthropic docs: x-api-key + anthropic-version: 2023-06-01
        return {
            "x-api-key": credentials.secret_value(),
            "anthropic-version": "2023-06-01",
        }


class GrokVerifier(_BaseProviderVerifier):
    """Proves a Grok key via GET /v1/models with Bearer auth."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # xAI uses OpenAI-compatible Bearer on https://api.x.ai/v1/models.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Exact string per xAI docs: Authorization: Bearer $XAI_API_KEY
        return {"Authorization": f"Bearer {credentials.secret_value()}"}


class DeepSeekVerifier(_BaseProviderVerifier):
    """Proves a DeepSeek key via GET /v1/models with Bearer auth."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # DeepSeek is OpenAI-compatible on https://api.deepseek.com/v1/models.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Per DeepSeek docs: Authorization: Bearer $DEEPSEEK_API_KEY
        return {"Authorization": f"Bearer {credentials.secret_value()}"}


class GlmVerifier(_BaseProviderVerifier):
    """Proves a GLM key via GET /models with Bearer auth."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # Z.AI is OpenAI-compatible on https://api.z.ai/api/paas/v4/models.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Per Z.AI docs: Authorization: Bearer $ZAI_API_KEY
        return {"Authorization": f"Bearer {credentials.secret_value()}"}


class MuseVerifier(_BaseProviderVerifier):
    """Proves a Muse key via GET /v1/models with Bearer auth."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # Meta is OpenAI-compatible on https://api.meta.ai/v1/models.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Per Meta docs: Authorization: Bearer $MODEL_API_KEY
        return {"Authorization": f"Bearer {credentials.secret_value()}"}


class GeminiVerifier(_BaseProviderVerifier):
    """Proves a Gemini key via GET /v1beta/models with x-goog-api-key."""

    def verify(self, credentials: ProviderCredentials) -> ProviderIdentity:
        # Google uses x-goog-api-key on generativelanguage.googleapis.com.
        self._probe(credentials, timeout_seconds=15.0)
        return ProviderIdentity(provider=credentials.provider)

    def _headers(self, credentials: ProviderCredentials) -> dict[str, str]:
        # Per Google docs: x-goog-api-key: $GEMINI_API_KEY
        return {"x-goog-api-key": credentials.secret_value()}


def verifier_for_provider(provider: Provider) -> ProviderVerifier:
    # Factory keeps command branching closed over Provider variants.
    if provider == Provider.OPENAI:
        return OpenAIVerifier()
    if provider == Provider.CLAUDE:
        return ClaudeVerifier()
    if provider == Provider.GROK:
        return GrokVerifier()
    if provider == Provider.DEEPSEEK:
        return DeepSeekVerifier()
    if provider == Provider.GLM:
        return GlmVerifier()
    if provider == Provider.MUSE:
        return MuseVerifier()
    if provider == Provider.GEMINI:
        return GeminiVerifier()
    raise ValueError(f"unsupported provider {provider}")
