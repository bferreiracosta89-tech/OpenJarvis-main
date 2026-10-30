"""Password and passkey authentication endpoints for the local JARVIS app."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from openjarvis.server.auth_store import AuthStore, Principal, webauthn_options_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
app_keys_router = APIRouter(prefix="/api/app-keys", tags=["app-keys"])


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = ""


class PasswordLoginRequest(BaseModel):
    identifier: str
    password: str


class VerifyCredentialRequest(BaseModel):
    credential: dict[str, Any]


class AppKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["chat"])


def _store(request: Request) -> AuthStore:
    return request.app.state.auth_store


def _public_session(store: AuthStore, user_id: str, token: str) -> dict[str, Any]:
    return {"token": token, "user": store.user_public(user_id)}


def _principal(request: Request, *, allowed_kinds: tuple[str, ...] = ("session", "server")) -> Principal:
    principal = getattr(request.state, "auth", None)
    if principal is None or principal.kind not in allowed_kinds or not principal.user_id:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    return principal


def _rp_context(request: Request) -> tuple[str, str]:
    origin = os.environ.get("OPENJARVIS_AUTH_ORIGIN", "").strip()
    if not origin:
        origin = request.headers.get("origin", "").strip().rstrip("/")
    if not origin:
        origin = str(request.base_url).rstrip("/")
    rp_id = os.environ.get("OPENJARVIS_AUTH_RP_ID", "").strip() or (request.url.hostname or "localhost")
    return rp_id, origin


@router.get("/bootstrap")
async def bootstrap(request: Request) -> dict[str, Any]:
    store = _store(request)
    return {"configured": store.has_users(), "passkeys_supported": True, "rp_id": _rp_context(request)[0]}


@router.post("/register")
async def register(body: RegisterRequest, request: Request) -> dict[str, Any]:
    store = _store(request)
    if store.has_users() and getattr(request.state, "auth", None) is None:
        raise HTTPException(status_code=409, detail="A conta local já foi criada")
    try:
        user = store.create_user(body.email, body.password, body.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    token = store.create_session(user["id"])
    return _public_session(store, user["id"], token)


@router.post("/password/login")
async def password_login(body: PasswordLoginRequest, request: Request) -> dict[str, Any]:
    store = _store(request)
    user = store.verify_password(body.identifier, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return _public_session(store, user["id"], store.create_session(user["id"]))


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    user = _store(request).user_public(principal.user_id or "")
    if user is None:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return {"user": user, "auth_method": principal.kind}


@router.post("/logout")
async def logout(request: Request) -> dict[str, str]:
    _, _, token = request.headers.get("authorization", "").partition(" ")
    if token:
        _store(request).revoke_session(token)
    return {"status": "logged_out"}


@router.post("/passkeys/register/options")
async def passkey_register_options(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    store = _store(request)
    user = store.user_public(principal.user_id or "")
    if user is None:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    try:
        from webauthn import base64url_to_bytes, generate_registration_options
        from webauthn.helpers.structs import (
            AuthenticatorAttachment,
            AuthenticatorSelectionCriteria,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )

        rp_id, origin = _rp_context(request)
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="OpenJarvis",
            user_id=user["id"].encode("utf-8"),
            user_name=user["email"],
            user_display_name=user["display_name"],
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            timeout=120_000,
        )
        data = webauthn_options_to_dict(options)
        store.save_challenge(base64url_to_bytes(data["challenge"]), "registration", user["id"], rp_id, origin)
        return data
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Dependência WebAuthn não instalada") from exc
    except Exception as exc:
        logger.exception("Unable to create passkey registration options")
        raise HTTPException(status_code=500, detail="Não foi possível iniciar a biometria") from exc


@router.post("/passkeys/register/verify")
async def passkey_register_verify(body: VerifyCredentialRequest, request: Request) -> dict[str, str]:
    principal = _principal(request)
    credential = body.credential
    try:
        from webauthn import base64url_to_bytes, verify_registration_response

        client_data = credential.get("response", {}).get("clientDataJSON", "")
        client_json = json.loads(base64url_to_bytes(client_data).decode("utf-8"))
        challenge = base64url_to_bytes(client_json["challenge"])
        stored = _store(request).consume_challenge(challenge, "registration")
        if stored is None or stored.get("user_id") != principal.user_id:
            raise HTTPException(status_code=400, detail="Desafio de biometria expirado")
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=stored["rp_id"],
            expected_origin=stored["origin"],
            require_user_verification=True,
        )
        transports = credential.get("response", {}).get("transports", [])
        _store(request).save_passkey(
            credential_id=verification.credential_id,
            user_id=principal.user_id or "",
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
            device_type=getattr(verification, "credential_device_type", None),
            backed_up=getattr(verification, "credential_backed_up", None),
            transports=transports if isinstance(transports, list) else [],
        )
        return {"status": "registered"}
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Dependência WebAuthn não instalada") from exc
    except Exception as exc:
        logger.warning("Passkey registration failed: %s", exc)
        raise HTTPException(status_code=400, detail="A validação biométrica falhou") from exc


@router.post("/passkeys/login/options")
async def passkey_login_options(request: Request) -> dict[str, Any]:
    try:
        from webauthn import base64url_to_bytes, generate_authentication_options
        from webauthn.helpers.structs import UserVerificationRequirement

        rp_id, origin = _rp_context(request)
        options = generate_authentication_options(
            rp_id=rp_id,
            user_verification=UserVerificationRequirement.REQUIRED,
            timeout=120_000,
        )
        data = webauthn_options_to_dict(options)
        store = _store(request)
        store.save_challenge(base64url_to_bytes(data["challenge"]), "authentication", None, rp_id, origin)
        return data
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Dependência WebAuthn não instalada") from exc
    except Exception as exc:
        logger.exception("Unable to create passkey authentication options")
        raise HTTPException(status_code=500, detail="Não foi possível iniciar a biometria") from exc


@router.post("/passkeys/login/verify")
async def passkey_login_verify(body: VerifyCredentialRequest, request: Request) -> dict[str, Any]:
    credential = body.credential
    try:
        from webauthn import base64url_to_bytes, verify_authentication_response

        credential_id = base64url_to_bytes(credential["rawId"])
        saved_key = _store(request).get_passkey(credential_id)
        if saved_key is None:
            raise HTTPException(status_code=401, detail="Biometria não cadastrada")
        client_data = credential.get("response", {}).get("clientDataJSON", "")
        client_json = json.loads(base64url_to_bytes(client_data).decode("utf-8"))
        challenge = base64url_to_bytes(client_json["challenge"])
        stored = _store(request).consume_challenge(challenge, "authentication")
        if stored is None:
            raise HTTPException(status_code=400, detail="Desafio de biometria expirado")
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=stored["rp_id"],
            expected_origin=stored["origin"],
            credential_public_key=base64url_to_bytes(saved_key["public_key"]),
            credential_current_sign_count=int(saved_key["sign_count"]),
            require_user_verification=True,
        )
        _store(request).update_passkey_use(credential_id, verification.new_sign_count)
        user_id = saved_key["user_id"]
        return _public_session(_store(request), user_id, _store(request).create_session(user_id))
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Dependência WebAuthn não instalada") from exc
    except Exception as exc:
        logger.warning("Passkey authentication failed: %s", exc)
        raise HTTPException(status_code=401, detail="A validação biométrica falhou") from exc


@app_keys_router.get("")
async def list_app_keys(request: Request) -> dict[str, Any]:
    principal = _principal(request)
    return {"keys": _store(request).list_app_keys(principal.user_id or "")}


@app_keys_router.post("")
async def create_app_key(body: AppKeyCreateRequest, request: Request) -> dict[str, Any]:
    principal = _principal(request)
    try:
        metadata, secret = _store(request).create_app_key(principal.user_id or "", body.name, body.scopes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"key": metadata, "secret": secret}


@app_keys_router.delete("/{key_id}")
async def revoke_app_key(key_id: str, request: Request) -> dict[str, Any]:
    principal = _principal(request)
    if not _store(request).revoke_app_key(principal.user_id or "", key_id):
        raise HTTPException(status_code=404, detail="Chave não encontrada ou já revogada")
    return {"status": "revoked", "id": key_id}


__all__ = ["app_keys_router", "router"]
