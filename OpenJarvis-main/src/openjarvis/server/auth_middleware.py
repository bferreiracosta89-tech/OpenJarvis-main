"""API key authentication middleware for the OpenJarvis server."""

from __future__ import annotations

import base64
import logging
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_WS_AUTH_PROTOCOL = "openjarvis.auth.v1"
_WS_KEY_PROTOCOL_PREFIX = "openjarvis.key.b64url."


def _api_keys_match(presented: str, expected: str) -> bool:
    """Compare API keys as bytes so non-ASCII values do not raise ``TypeError``."""
    try:
        presented_bytes = presented.encode("utf-8")
        expected_bytes = expected.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return secrets.compare_digest(presented_bytes, expected_bytes)


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates ``Authorization: Bearer <key>`` on ``/v1/*`` and ``/api/*`` routes.

    Webhook routes and health checks are exempt — they use
    per-channel signature verification instead.
    """

    def __init__(self, app, api_key: str = "") -> None:  # noqa: ANN001
        super().__init__(app)
        self._api_key = api_key or os.environ.get("OPENJARVIS_API_KEY", "")

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        # Browser CORS preflights never carry Authorization, and rejecting
        # them here means they never reach CORSMiddleware to get
        # Access-Control-Allow-* headers, breaking cross-origin access
        # outright (#758). Do not exempt arbitrary OPTIONS requests: a real
        # preflight is identified by both headers required by the CORS protocol.
        if self._is_cors_preflight(request):
            return await call_next(request)
        if self._is_public(request.url.path):
            return await call_next(request)
        if self._requires_auth(request.url.path):
            auth = request.headers.get("Authorization", "")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() != "bearer":
                token = ""
            valid_global = bool(self._api_key and _api_keys_match(token, self._api_key))
            principal = None
            store = getattr(request.app.state, "auth_store", None)
            if store is not None and token and not valid_global:
                principal = store.authenticate(token)
            if not valid_global and principal is None:
                # Keep first-run local servers usable so the first account can
                # be created. Once an account exists, API calls need a session
                # or an independently issued application key.
                if store is None or store.has_users() or self._api_key:
                    return JSONResponse({"detail": "Autenticação necessária"}, status_code=401)
            if valid_global:
                request.state.auth = type("ServerPrincipal", (), {"kind": "server", "user_id": None, "scopes": ()})()
            else:
                request.state.auth = principal
            if principal is not None and getattr(principal, "kind", "") == "app_key":
                required_scope = self._required_scope(request.url.path)
                scopes = set(getattr(principal, "scopes", ()))
                # ``read`` is an additive read-only scope. Mutating requests
                # must carry the functional scope (chat/projects/agents).
                if required_scope and required_scope not in scopes and not (
                    request.method in {"GET", "HEAD"} and "read" in scopes
                ):
                    return JSONResponse(
                        {"detail": f"A chave não possui o escopo '{required_scope}'"},
                        status_code=403,
                    )
        return await call_next(request)

    @staticmethod
    def _is_cors_preflight(request: Request) -> bool:
        return (
            request.method == "OPTIONS"
            and bool(request.headers.get("Origin"))
            and bool(request.headers.get("Access-Control-Request-Method"))
        )

    @staticmethod
    def _requires_auth(path: str) -> bool:
        """Protect API routes, metrics and API docs; leave the UI/health open.

        ``/metrics`` exposes request/token counters that should not be readable
        by unauthenticated clients, so it is gated alongside ``/v1`` and
        ``/api``. ``/health`` stays open for liveness probes.

        The OpenAPI schema and its viewers (``/openapi.json``, ``/docs``,
        ``/redoc``) are gated too: on an exposed deployment they hand an
        unauthenticated client a complete map of every route, parameter and
        payload shape — useful reconnaissance for probing the authenticated
        endpoints. This only applies when an API key is configured at all, so
        keyless local use is unchanged.
        """
        return (
            path.startswith("/v1/")
            or path.startswith("/api/")
            or path == "/metrics"
            or path.startswith("/metrics/")
            or path in ("/openapi.json", "/docs", "/redoc")
            or path.startswith("/docs/")
            or path.startswith("/redoc/")
        )

    @staticmethod
    def _is_public(path: str) -> bool:
        # Only bootstrap and the password/passkey login ceremony are public.
        # Account/session management and passkey registration must already have
        # an authenticated principal; otherwise ``request.state.auth`` would
        # never be populated for those handlers.
        return path in {
            "/health",
            "/api/auth/bootstrap",
            "/api/auth/register",
            "/api/auth/password/login",
            "/api/auth/passkeys/login/options",
            "/api/auth/passkeys/login/verify",
        }

    @staticmethod
    def _required_scope(path: str) -> str | None:
        if path.startswith("/api/workspace/projects"):
            return "projects"
        if path.startswith("/api/workspace/tasks") or path.startswith("/api/workspace/conclaves"):
            return "agents"
        if path.startswith("/api/workspace/"):
            return "chat"
        if path.startswith("/v1/managed-agents") or path.startswith("/v1/agents"):
            return "agents"
        if path.startswith("/v1/"):
            return "chat"
        return None


def generate_api_key() -> str:
    """Generate a new API key with ``oj_sk_`` prefix."""
    return f"oj_sk_{secrets.token_urlsafe(32)}"


def check_bind_safety(host: str, *, api_key: str) -> None:
    """Refuse to bind non-loopback without an API key.

    Raises ``SystemExit`` if *host* is not a loopback address and
    *api_key* is empty.
    """
    import ipaddress
    import sys

    try:
        is_loop = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loop = host in ("localhost", "")

    if not is_loop and not api_key:
        logger.error(
            "Binding to %s requires OPENJARVIS_API_KEY to be set. "
            "Run: jarvis auth generate-key",
            host,
        )
        sys.exit(1)


def _websocket_key_protocol(api_key: str) -> str:
    """Encode an API key as a browser-safe WebSocket protocol token."""
    try:
        encoded = base64.urlsafe_b64encode(api_key.encode("utf-8")).decode("ascii")
    except UnicodeEncodeError:
        return ""
    return f"{_WS_KEY_PROTOCOL_PREFIX}{encoded.rstrip('=')}"


def _offered_websocket_auth(websocket) -> tuple[str, str | None]:  # noqa: ANN001
    """Return the credential protocol and protocol to negotiate, if well formed.

    ASGI exposes the complete, flattened protocol offer in ``scope``. Reading
    it avoids ambiguity from repeated ``Sec-WebSocket-Protocol`` header fields.
    Exactly one stable protocol marker and one encoded credential are required.
    """
    offered = getattr(websocket, "scope", {}).get("subprotocols", [])
    if not isinstance(offered, (list, tuple)) or len(offered) != 2:
        return "", None
    if offered.count(_WS_AUTH_PROTOCOL) != 1:
        return "", None
    credentials = [
        protocol
        for protocol in offered
        if isinstance(protocol, str) and protocol != _WS_AUTH_PROTOCOL
    ]
    if len(credentials) != 1 or not credentials[0].startswith(_WS_KEY_PROTOCOL_PREFIX):
        return "", None
    if credentials[0] == _WS_KEY_PROTOCOL_PREFIX:
        return "", None
    return credentials[0], _WS_AUTH_PROTOCOL


def authenticate_websocket(
    websocket,  # noqa: ANN001
    expected_key: str,
    auth_store=None,  # noqa: ANN001
    required_scope: str | None = None,
) -> tuple[bool, str | None]:
    """Authenticate a WebSocket and return its negotiated auth subprotocol.

    Programmatic clients can send ``Authorization: Bearer <key>``. Browser
    clients, which cannot set that header, offer ``openjarvis.auth.v1`` plus a
    marked, unpadded base64url encoding of the UTF-8 key. The encoding only
    makes the credential valid subprotocol syntax; it does not make it secret.
    """
    credential_protocol, selected_protocol = _offered_websocket_auth(websocket)

    auth = websocket.headers.get("authorization", "")
    scheme, _, header_token = auth.partition(" ")
    header_valid = scheme.lower() == "bearer" and _api_keys_match(
        header_token, expected_key
    )

    expected_protocol = _websocket_key_protocol(expected_key)
    protocol_valid = bool(credential_protocol and expected_protocol) and (
        _api_keys_match(credential_protocol, expected_protocol)
    )
    if header_valid or protocol_valid:
        return True, selected_protocol

    raw_token = header_token if scheme.lower() == "bearer" else ""
    if not raw_token and credential_protocol:
        encoded = credential_protocol[len(_WS_KEY_PROTOCOL_PREFIX):]
        try:
            raw_token = base64.urlsafe_b64decode(
                encoded + "=" * (-len(encoded) % 4)
            ).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raw_token = ""
    if auth_store is not None and raw_token:
        principal = auth_store.authenticate(raw_token)
        scopes = set(getattr(principal, "scopes", ())) if principal is not None else set()
        if principal is not None and (required_scope is None or required_scope in scopes):
            return True, selected_protocol

    # Preserve keyless local development only until the first local account is
    # created. Account-enabled WebSockets require a session/app credential.
    if not expected_key and (auth_store is None or not auth_store.has_users()):
        return True, selected_protocol
    return False, selected_protocol


def websocket_authorized(websocket, expected_key: str, auth_store=None) -> bool:  # noqa: ANN001
    """Return ``True`` if a WebSocket connection presents the expected key.

    ``AuthMiddleware`` is a ``BaseHTTPMiddleware`` and never sees WebSocket
    upgrade requests, so streaming endpoints must check the token themselves
    in the handshake before calling ``websocket.accept()``.

    When *expected_key* is empty, authentication is disabled (the loopback /
    local-only default, matching :class:`AuthMiddleware`) and all connections
    are allowed. See :func:`authenticate_websocket` for the supported
    credential transports. URL query parameters are deliberately not accepted
    because request targets commonly appear in access logs and browser history.
    """
    return authenticate_websocket(websocket, expected_key, auth_store)[0]
