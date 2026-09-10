"""GitHub OAuth device-flow adapter and bounded REST reads.

The first local GitHub connection uses an OAuth App device flow, which works in terminals without
a callback listener. Repository and pull-request reads stay on the selected API paths.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import SecretStr, ValidationError

from ....types.connection import (
    ConnectionIdentity,
    ConnectionProvider,
    ConnectionRead,
    ConnectionResource,
    ConnectionToken,
)
from ...errors.failures import (
    ConnectionOAuthFailed,
    ConnectionProtocolError,
    ConnectionReauthenticationRequired,
    ConnectionResourceUnavailable,
)
from ..oauth import OAuthBrowser
from .base import AuthenticatedConnection, ProviderAdapterBase

if TYPE_CHECKING:
    from ...runtime.context import ApplicationContext

_GITHUB_PROVIDER = "github"
_GITHUB_API = "https://api.github.com"
_GITHUB_DEVICE_URL = "https://github.com/login/device/code"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_DEFAULT_SCOPES = ("read:user", "repo")


class GitHubConnectionAdapter(ProviderAdapterBase):
    """Authenticates GitHub and reads repositories or pull requests."""

    provider = ConnectionProvider.GITHUB

    def login(self, context: ApplicationContext, scopes: tuple[str, ...], client_secrets_path: Path | None = None) -> AuthenticatedConnection:  # fmt: skip  # noqa: E501
        # Runs device authorization, exchanges the approval, and verifies GitHub identity.
        del client_secrets_path
        client_id = context.environment.get("VIDBYTE_GITHUB_CLIENT_ID", "").strip()
        if not client_id:
            from ...errors.failures import ConnectionConfigurationInvalid

            raise ConnectionConfigurationInvalid(_GITHUB_PROVIDER)
        requested_scopes = scopes or _DEFAULT_SCOPES
        client = self._client(context, _GITHUB_PROVIDER)
        device = client.post_form(
            _GITHUB_DEVICE_URL,
            {"client_id": client_id, "scope": " ".join(requested_scopes)},
            self._oauth_headers(),
        )
        device_code = self._text(device, "device_code", _GITHUB_PROVIDER)
        user_code = self._text(device, "user_code", _GITHUB_PROVIDER)
        expires_in = self._integer(device, "expires_in", _GITHUB_PROVIDER)
        interval = self._optional_integer(device, "interval") or 5
        verification_url = self._optional_text(device, "verification_uri_complete") or self._text(
            device, "verification_uri", _GITHUB_PROVIDER
        )
        context.output().diagnostic(
            f"GitHub device authorization: enter code {user_code} at {verification_url}"
        )
        OAuthBrowser().open(verification_url, context.streams)
        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            token_payload = client.post_form(
                _GITHUB_TOKEN_URL,
                {
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                self._oauth_headers(),
            )
            outcome = token_payload.get("error")
            if outcome == "authorization_pending":
                time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
                continue
            if outcome == "slow_down":
                interval += 5
                time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
                continue
            if isinstance(outcome, str) and outcome:
                raise ConnectionOAuthFailed(_GITHUB_PROVIDER)
            token = self._token_from_payload(token_payload, requested_scopes)
            identity = self.verify(context, token)
            return AuthenticatedConnection(token=token, identity=identity)
        raise ConnectionOAuthFailed(
            _GITHUB_PROVIDER,
            TimeoutError("device authorization timed out"),
        )

    def verify(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionIdentity:
        # Calls GitHub's user endpoint and returns only stable identity metadata.
        payload = self._client(context, _GITHUB_PROVIDER).get_json(
            f"{_GITHUB_API}/user",
            self._headers(token),
        )
        account_id = payload.get("id")
        if isinstance(account_id, bool) or not isinstance(account_id, (int, str)):
            raise ConnectionProtocolError(_GITHUB_PROVIDER, ValueError("missing user id"))
        account_label = self._optional_text(payload, "login")
        return ConnectionIdentity(
            provider=self.provider,
            account_id=str(account_id),
            account_label=account_label,
            scopes=self._scopes(token.provider_data.get("scopes")),
        )

    def refresh(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionToken:
        # Exchanges a GitHub refresh token when the OAuth App issues expiring tokens.
        refresh_token = token.refresh_secret()
        if refresh_token is None:
            raise ConnectionReauthenticationRequired(_GITHUB_PROVIDER)
        client_id = context.environment.get("VIDBYTE_GITHUB_CLIENT_ID", "").strip()
        if not client_id:
            from ...errors.failures import ConnectionConfigurationInvalid

            raise ConnectionConfigurationInvalid(_GITHUB_PROVIDER)
        values = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        client_secret = context.environment.get("VIDBYTE_GITHUB_CLIENT_SECRET", "").strip()
        if client_secret:
            values["client_secret"] = client_secret
        payload = self._client(context, _GITHUB_PROVIDER).post_form(
            _GITHUB_TOKEN_URL, values, self._oauth_headers()
        )
        if isinstance(payload.get("error"), str):
            raise ConnectionReauthenticationRequired(_GITHUB_PROVIDER)
        return self._token_from_payload(
            payload,
            self._scopes(payload.get("scope")) or self._scopes(token.provider_data.get("scopes")),
            old_refresh=refresh_token,
        )

    def read(self, context: ApplicationContext, token: ConnectionToken, resource: ConnectionResource) -> ConnectionRead:  # fmt: skip  # noqa: E501
        # Reads exactly one validated repository or pull request endpoint.
        self._resource_for(resource, self.provider)
        owner, repository = self._repository_parts(resource.identifier)
        if resource.resource_type == "repo":
            path = f"{_GITHUB_API}/repos/{owner}/{repository}"
        elif resource.resource_type == "pull-request" and resource.number is not None:
            if resource.number < 1:
                raise ConnectionProtocolError(_GITHUB_PROVIDER, ValueError("pull request number"))
            path = f"{_GITHUB_API}/repos/{owner}/{repository}/pulls/{resource.number}"
        else:
            raise ConnectionResourceUnavailable(_GITHUB_PROVIDER)
        payload = self._client(context, _GITHUB_PROVIDER).get_json(path, self._headers(token))
        return ConnectionRead(
            provider=self.provider,
            resource_type=resource.resource_type,
            identifier=resource.identifier,
            data=self._json_data(payload, _GITHUB_PROVIDER),
        )

    def revoke(self, context: ApplicationContext, token: ConnectionToken) -> None:
        # Revokes an OAuth App token only when the configured client can authenticate that call.
        import httpx

        client_id = context.environment.get("VIDBYTE_GITHUB_CLIENT_ID", "").strip()
        client_secret = context.environment.get("VIDBYTE_GITHUB_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return
        try:
            with httpx.Client(
                timeout=context.options.request_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = client.request(
                    "DELETE",
                    f"{_GITHUB_API}/applications/{client_id}/token",
                    auth=(client_id, client_secret),
                    content=json.dumps({"access_token": token.access_secret()}),
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Content-Type": "application/json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
        except httpx.HTTPError as error:
            raise ConnectionOAuthFailed(_GITHUB_PROVIDER, error) from error
        if response.status_code >= 300:
            raise ConnectionOAuthFailed(_GITHUB_PROVIDER)

    def _headers(self, token: ConnectionToken) -> dict[str, str]:
        # Pins GitHub REST requests to the documented media type and API version.
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token.access_secret()}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _oauth_headers(self) -> dict[str, str]:
        # Requests JSON from GitHub's OAuth endpoints instead of form-encoded responses.
        return {"Accept": "application/json"}

    def _token_from_payload(self, payload: dict[str, object], requested_scopes: tuple[str, ...], old_refresh: str | None = None) -> ConnectionToken:  # fmt: skip  # noqa: E501
        # Converts a successful GitHub token response while retaining refresh rotation state.
        access_token = self._text(payload, "access_token", _GITHUB_PROVIDER)
        refresh_token = self._optional_text(payload, "refresh_token") or old_refresh
        expires_in = self._optional_integer(payload, "expires_in")
        scopes = self._scopes(payload.get("scope")) or requested_scopes
        try:
            return ConnectionToken(
                access_token=SecretStr(access_token),
                refresh_token=SecretStr(refresh_token) if refresh_token is not None else None,
                token_type=self._optional_text(payload, "token_type") or "Bearer",
                expires_at=int(time.time()) + expires_in if expires_in is not None else None,
                provider_data={"scopes": " ".join(scopes)},
            )
        except ValidationError as error:
            raise ConnectionProtocolError(_GITHUB_PROVIDER, error) from error

    def _repository_parts(self, identifier: str) -> tuple[str, str]:
        # Validates owner/repository before either value reaches a URL path.
        parts = identifier.split("/")
        if len(parts) != 2 or not all(parts):
            raise ConnectionProtocolError(
                _GITHUB_PROVIDER,
                ValueError("repository must be owner/name"),
            )
        return (
            self._path_component(parts[0], _GITHUB_PROVIDER),
            self._path_component(parts[1], _GITHUB_PROVIDER),
        )
