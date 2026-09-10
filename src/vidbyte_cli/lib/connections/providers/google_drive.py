"""Google Drive installed-app OAuth adapter and bounded file reads.

The adapter uses PKCE and a loopback callback, then reads Drive metadata and content only for
the file identifier selected by the caller.
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote, urlencode, urlparse

from pydantic import SecretStr, ValidationError

from ....types.connection import (
    ConnectionIdentity,
    ConnectionProvider,
    ConnectionRead,
    ConnectionResource,
    ConnectionToken,
)
from ...errors.failures import (
    ConnectionConfigurationInvalid,
    ConnectionOAuthFailed,
    ConnectionProtocolError,
    ConnectionReauthenticationRequired,
    ConnectionResourceUnavailable,
)
from ..oauth import OAuthBrowser, OAuthCallbackServer, PkceChallenge
from .base import AuthenticatedConnection, ProviderAdapterBase

if TYPE_CHECKING:
    from ...runtime.context import ApplicationContext

_GOOGLE_PROVIDER = "google-drive"
_GOOGLE_AUTH_DEFAULT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_DEFAULT = "https://oauth2.googleapis.com/token"
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_GOOGLE_DRIVE_API = "https://www.googleapis.com/drive/v3"
_DEFAULT_SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
_WORKSPACE_EXPORTS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "application/pdf",
}


class GoogleClientConfig:
    """Validated installed-app Google OAuth client settings."""

    def __init__(self, client_id: str, client_secret: str, auth_uri: str, token_uri: str) -> None:
        # Client secrets are held only during the flow and never enter connection metadata.
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_uri = auth_uri
        self.token_uri = token_uri

    @classmethod
    def from_file(cls, path: Path) -> GoogleClientConfig:
        # Reads the standard Google installed client JSON without copying it to CLI state.
        try:
            raw = path.read_bytes()
            if len(raw) > 1_048_576:
                raise ValueError("Google client configuration is oversized")
            payload = json.loads(raw)
            installed = payload.get("installed") if isinstance(payload, dict) else None
            if not isinstance(installed, dict):
                raise ValueError("Google client configuration has no installed client")
            client_id = installed.get("client_id")
            client_secret = installed.get("client_secret", "")
            auth_uri = installed.get("auth_uri", _GOOGLE_AUTH_DEFAULT)
            token_uri = installed.get("token_uri", _GOOGLE_TOKEN_DEFAULT)
            if not isinstance(client_id, str) or not client_id:
                raise ValueError("Google client ID is missing")
            if not isinstance(client_secret, str):
                raise ValueError("Google client secret is malformed")
            if not isinstance(auth_uri, str) or not auth_uri.startswith(
                "https://accounts.google.com/"
            ):
                raise ValueError("Google authorization endpoint is not trusted")
            if token_uri != _GOOGLE_TOKEN_DEFAULT:
                raise ValueError("Google token endpoint is not trusted")
            return cls(client_id, client_secret, auth_uri, token_uri)
        except (OSError, ValueError, TypeError) as error:
            raise ConnectionConfigurationInvalid(_GOOGLE_PROVIDER) from error


class GoogleDriveConnectionAdapter(ProviderAdapterBase):
    """Authenticates Google Drive and reads one selected file."""

    provider = ConnectionProvider.GOOGLE_DRIVE

    def login(self, context: ApplicationContext, scopes: tuple[str, ...], client_secrets_path: Path | None = None) -> AuthenticatedConnection:  # fmt: skip  # noqa: E501
        # Runs installed-app PKCE authorization and verifies the Google Drive identity.
        config = self._load_config(context, client_secrets_path)
        requested_scopes = scopes or _DEFAULT_SCOPES
        flow = PkceChallenge.generate()
        with OAuthCallbackServer(_GOOGLE_PROVIDER) as callback:
            authorization_url = self._authorization_url(
                config,
                callback.redirect_uri,
                flow,
                requested_scopes,
            )
            OAuthBrowser().open(authorization_url, context.streams)
            query = callback.wait(context.options.request_timeout_seconds)
        self._validate_callback(query, flow.state)
        code = query.get("code")
        if not code:
            raise ConnectionOAuthFailed(_GOOGLE_PROVIDER)
        values = {
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code_verifier": flow.verifier,
            "grant_type": "authorization_code",
            "redirect_uri": callback.redirect_uri,
        }
        payload = self._client(context, _GOOGLE_PROVIDER).post_form(config.token_uri, values)
        token = self._token_from_payload(payload, requested_scopes, client_config=config)
        return AuthenticatedConnection(token=token, identity=self.verify(context, token))

    def verify(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionIdentity:
        # Calls Drive about.user and returns account metadata without returning the token.
        payload = self._client(context, _GOOGLE_PROVIDER).get_json(
            f"{_GOOGLE_DRIVE_API}/about",
            self._headers(token),
            {"fields": "user"},
        )
        user = payload.get("user")
        if not isinstance(user, dict):
            raise ConnectionProtocolError(_GOOGLE_PROVIDER, ValueError("missing Drive user"))
        account_id = user.get("permissionId")
        email = user.get("emailAddress")
        display_name = user.get("displayName")
        if not isinstance(account_id, str) or not account_id:
            raise ConnectionProtocolError(
                _GOOGLE_PROVIDER,
                ValueError("missing Drive permission id"),
            )
        label = email if isinstance(email, str) and email else display_name
        return ConnectionIdentity(
            provider=self.provider,
            account_id=account_id,
            account_label=label if isinstance(label, str) and label else None,
            scopes=self._scopes(token.provider_data.get("scopes")),
        )

    def refresh(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionToken:
        # Refreshes an expired Drive token and retains a rotated refresh token when returned.
        refresh_token = token.refresh_secret()
        if refresh_token is None:
            raise ConnectionReauthenticationRequired(_GOOGLE_PROVIDER)
        config = self._refresh_config(context, token)
        payload = self._client(context, _GOOGLE_PROVIDER).post_form(
            config.token_uri,
            {
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return self._token_from_payload(
            payload,
            self._scopes(payload.get("scope")) or self._scopes(token.provider_data.get("scopes")),
            old_refresh=refresh_token,
        )

    def read(self, context: ApplicationContext, token: ConnectionToken, resource: ConnectionResource) -> ConnectionRead:  # fmt: skip  # noqa: E501
        # Fetches metadata and then bounded content for exactly one Drive file.
        self._resource_for(resource, self.provider)
        if resource.resource_type != "file":
            raise ConnectionResourceUnavailable(_GOOGLE_PROVIDER)
        file_id = self._file_id(resource.identifier)
        encoded_id = quote(file_id, safe="")
        metadata_payload = self._client(context, _GOOGLE_PROVIDER).get_json(
            f"{_GOOGLE_DRIVE_API}/files/{encoded_id}",
            self._headers(token),
            {"fields": "id,name,mimeType,modifiedTime,size,webViewLink"},
        )
        mime_type = self._text(metadata_payload, "mimeType", _GOOGLE_PROVIDER)
        if mime_type in _WORKSPACE_EXPORTS:
            content = self._client(context, _GOOGLE_PROVIDER).get_bytes(
                f"{_GOOGLE_DRIVE_API}/files/{encoded_id}/export",
                self._headers(token),
                {"mimeType": _WORKSPACE_EXPORTS[mime_type]},
            )
        else:
            content = self._client(context, _GOOGLE_PROVIDER).get_bytes(
                f"{_GOOGLE_DRIVE_API}/files/{encoded_id}",
                self._headers(token),
                {"alt": "media"},
            )
        data = self._json_data(metadata_payload, _GOOGLE_PROVIDER)
        try:
            data["content"] = content.decode("utf-8")
            data["content_encoding"] = "utf-8"
        except UnicodeDecodeError:
            data["content"] = base64.b64encode(content).decode("ascii")
            data["content_encoding"] = "base64"
        return ConnectionRead(
            provider=self.provider,
            resource_type=resource.resource_type,
            identifier=file_id,
            data=data,
        )

    def revoke(self, context: ApplicationContext, token: ConnectionToken) -> None:
        # Revokes a Google access token through Google's documented revoke endpoint.
        import httpx

        try:
            with httpx.Client(
                timeout=context.options.request_timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    _GOOGLE_REVOKE_URL,
                    data={"token": token.access_secret()},
                )
        except httpx.HTTPError as error:
            raise ConnectionOAuthFailed(_GOOGLE_PROVIDER, error) from error
        if response.status_code >= 300:
            raise ConnectionOAuthFailed(_GOOGLE_PROVIDER)

    def _load_config(self, context: ApplicationContext, explicit_path: Path | None) -> GoogleClientConfig:  # fmt: skip  # noqa: E501
        # Resolves an explicit option before the environment-selected client configuration.
        raw_path = explicit_path
        if raw_path is None:
            configured = context.environment.get("VIDBYTE_GOOGLE_CLIENT_SECRETS", "").strip()
            raw_path = Path(configured) if configured else None
        if raw_path is None:
            raise ConnectionConfigurationInvalid(_GOOGLE_PROVIDER)
        return GoogleClientConfig.from_file(raw_path)

    def _refresh_config(
        self, context: ApplicationContext, token: ConnectionToken
    ) -> GoogleClientConfig:
        # Uses current configuration when available, otherwise the keyring-scoped client details.
        configured = context.environment.get("VIDBYTE_GOOGLE_CLIENT_SECRETS", "").strip()
        if configured:
            return GoogleClientConfig.from_file(Path(configured))
        client_id = token.provider_data.get("client_id")
        client_secret = token.provider_data.get("client_secret", "")
        if not client_id:
            raise ConnectionConfigurationInvalid(_GOOGLE_PROVIDER)
        return GoogleClientConfig(
            client_id,
            client_secret,
            _GOOGLE_AUTH_DEFAULT,
            _GOOGLE_TOKEN_DEFAULT,
        )

    def _authorization_url(self, config: GoogleClientConfig, redirect_uri: str, flow: PkceChallenge, scopes: tuple[str, ...]) -> str:  # fmt: skip  # noqa: E501
        # Builds a URL carrying state and the PKCE challenge but never a bearer token.
        query = urlencode(
            {
                "client_id": config.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": flow.state,
                "code_challenge": flow.challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return f"{config.auth_uri}?{query}"

    def _validate_callback(self, query: dict[str, str], expected_state: str) -> None:
        # Rejects provider errors and forged callbacks before exchanging any authorization code.
        if query.get("state") != expected_state:
            from ...errors.failures import ConnectionOAuthStateInvalid

            raise ConnectionOAuthStateInvalid(_GOOGLE_PROVIDER)
        if query.get("error"):
            raise ConnectionOAuthFailed(_GOOGLE_PROVIDER)

    def _token_from_payload(self, payload: dict[str, object], scopes: tuple[str, ...], old_refresh: str | None = None, client_config: GoogleClientConfig | None = None) -> ConnectionToken:  # fmt: skip  # noqa: E501
        # Converts a Google token response and retains a refresh token omitted during rotation.
        access_token = self._text(payload, "access_token", _GOOGLE_PROVIDER)
        refresh_token = self._optional_text(payload, "refresh_token") or old_refresh
        expires_in = self._optional_integer(payload, "expires_in")
        provider_data = {"scopes": " ".join(self._scopes(payload.get("scope")) or scopes)}
        if client_config is not None:
            provider_data.update(
                {
                    "client_id": client_config.client_id,
                    "client_secret": client_config.client_secret,
                }
            )
        try:
            return ConnectionToken(
                access_token=SecretStr(access_token),
                refresh_token=SecretStr(refresh_token) if refresh_token is not None else None,
                token_type=self._optional_text(payload, "token_type") or "Bearer",
                expires_at=int(time.time()) + expires_in if expires_in is not None else None,
                provider_data=provider_data,
            )
        except ValidationError as error:
            raise ConnectionProtocolError(_GOOGLE_PROVIDER, error) from error

    def _file_id(self, value: str) -> str:
        # Accepts a Drive ID or common Drive/Docs URL and rejects unrelated URLs.
        candidate = value
        if "://" in value:
            parsed = urlparse(value)
            if parsed.netloc not in {"drive.google.com", "docs.google.com"}:
                raise ConnectionResourceUnavailable(_GOOGLE_PROVIDER)
            match = re.search(r"/d/([^/]+)", parsed.path)
            query_id = parse_qs(parsed.query).get("id", [None])[0]
            candidate = match.group(1) if match else query_id or ""
        return self._path_component(candidate, _GOOGLE_PROVIDER)
