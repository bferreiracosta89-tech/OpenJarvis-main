"""Local authentication and application-key persistence.

The store is intentionally SQLite-backed so the local server can run without
another service. Its schema uses relational primitives that can be migrated to
PostgreSQL/Neon later without changing the HTTP contract.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
CHALLENGE_TTL_SECONDS = 300


def _now() -> float:
    return time.time()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=16_384, r=8, p=1, dklen=64
    )


def _verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    return secrets.compare_digest(_hash_password(password, salt), expected)


@dataclass(frozen=True)
class Principal:
    subject: str
    kind: str
    user_id: str | None = None
    scopes: tuple[str, ...] = ()


class AuthStore:
    """SQLite store for users, sessions, passkeys, and application keys."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from openjarvis.core.paths import get_config_dir

            # Keep the local backend in one database so authentication and
            # workspace data can be moved to Neon/Postgres as one schema later.
            config_dir = get_config_dir()
            db_path = config_dir / "workspace.db"
            # Preserve installations created by the earlier auth-only
            # implementation. The copy is performed only when the new DB does
            # not exist, so a later restart never overwrites workspace data.
            legacy_db = config_dir / "auth.db"
            if not Path(db_path).exists() and legacy_db.exists():
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                Path(db_path).write_bytes(legacy_db.read_bytes())
        self.db_path = str(Path(db_path).expanduser()) if str(db_path) != ":memory:" else ":memory:"
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
                CREATE TABLE IF NOT EXISTS auth_challenges (
                    challenge_hash TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    user_id TEXT REFERENCES auth_users(id) ON DELETE CASCADE,
                    rp_id TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_passkeys (
                    credential_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    public_key TEXT NOT NULL,
                    sign_count INTEGER NOT NULL DEFAULT 0,
                    device_type TEXT,
                    backed_up INTEGER,
                    transports_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    last_used_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_passkeys_user ON auth_passkeys(user_id);
                CREATE TABLE IF NOT EXISTS auth_app_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    scopes_json TEXT NOT NULL DEFAULT '["chat"]',
                    created_at REAL NOT NULL,
                    last_used_at REAL,
                    revoked_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_app_keys_user ON auth_app_keys(user_id);
                """
            )

    def has_users(self) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None

    def create_user(self, email: str, password: str, display_name: str = "") -> dict[str, Any]:
        email = email.strip().lower()
        display_name = display_name.strip() or email.split("@", 1)[0]
        if not email or "@" not in email:
            raise ValueError("Informe um e-mail válido")
        if len(password) < 8:
            raise ValueError("A senha precisa ter pelo menos 8 caracteres")
        user_id = f"usr_{secrets.token_urlsafe(18)}"
        salt = secrets.token_bytes(16)
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO auth_users
                    (id, email, display_name, password_salt, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, email, display_name, salt, _hash_password(password, salt), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Já existe uma conta local") from exc
        return self.user_public(user_id) or {}

    def user_public(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, display_name, created_at FROM auth_users WHERE id = ? AND disabled = 0",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def verify_password(self, identifier: str, password: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_users WHERE lower(email) = lower(?) AND disabled = 0",
                (identifier.strip(),),
            ).fetchone()
        if row is None or not _verify_password(password, row["password_salt"], row["password_hash"]):
            return None
        return self.user_public(row["id"])

    def create_session(self, user_id: str) -> str:
        raw = f"oj_session_{secrets.token_urlsafe(40)}"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_sessions(token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (_hash_token(raw), user_id, now, now + SESSION_TTL_SECONDS, now),
            )
        return raw

    def revoke_session(self, raw_token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_hash_token(raw_token),))

    def authenticate(self, raw_token: str) -> Principal | None:
        if not raw_token:
            return None
        token_hash = _hash_token(raw_token)
        now = _now()
        with self._connect() as conn:
            session = conn.execute(
                "SELECT user_id FROM auth_sessions WHERE token_hash = ? AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if session is not None:
                conn.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?", (now, token_hash))
                return Principal(subject=session["user_id"], kind="session", user_id=session["user_id"])
            app_key = conn.execute(
                "SELECT id, user_id, scopes_json FROM auth_app_keys WHERE key_hash = ? AND revoked_at IS NULL",
                (token_hash,),
            ).fetchone()
            if app_key is not None:
                conn.execute("UPDATE auth_app_keys SET last_used_at = ? WHERE id = ?", (now, app_key["id"]))
                return Principal(
                    subject=app_key["id"],
                    kind="app_key",
                    user_id=app_key["user_id"],
                    scopes=tuple(json.loads(app_key["scopes_json"] or "[]")),
                )
        return None

    def save_challenge(self, challenge: bytes, kind: str, user_id: str | None, rp_id: str, origin: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO auth_challenges
                   (challenge_hash, kind, user_id, rp_id, origin, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_hash_token(_b64(challenge)), kind, user_id, rp_id, origin, now, now + CHALLENGE_TTL_SECONDS),
            )

    def consume_challenge(self, challenge: bytes, kind: str) -> dict[str, Any] | None:
        challenge_hash = _hash_token(_b64(challenge))
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM auth_challenges WHERE challenge_hash = ? AND kind = ? AND expires_at > ?",
                (challenge_hash, kind, _now()),
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM auth_challenges WHERE challenge_hash = ?", (challenge_hash,))
        return dict(row)

    def save_passkey(self, *, credential_id: bytes, user_id: str, public_key: bytes, sign_count: int, device_type: str | None, backed_up: bool | None, transports: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO auth_passkeys
                   (credential_id, user_id, public_key, sign_count, device_type, backed_up, transports_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM auth_passkeys WHERE credential_id = ?), ?))""",
                (_b64(credential_id), user_id, _b64(public_key), sign_count, device_type,
                 None if backed_up is None else int(backed_up), json.dumps(transports), _b64(credential_id), _now()),
            )

    def get_passkey(self, credential_id: bytes) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_passkeys WHERE credential_id = ?", (_b64(credential_id),)).fetchone()
        return dict(row) if row else None

    def update_passkey_use(self, credential_id: bytes, sign_count: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE auth_passkeys SET sign_count = ?, last_used_at = ? WHERE credential_id = ?", (sign_count, _now(), _b64(credential_id)))

    def list_app_keys(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, key_prefix, scopes_json, created_at, last_used_at, revoked_at FROM auth_app_keys WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["scopes"] = json.loads(item.pop("scopes_json") or "[]")
            item["revoked"] = item["revoked_at"] is not None
            result.append(item)
        return result

    def create_app_key(self, user_id: str, name: str, scopes: list[str]) -> tuple[dict[str, Any], str]:
        name = name.strip()
        allowed = {"chat", "agents", "projects", "read"}
        if not name:
            raise ValueError("Informe um nome para a chave")
        if not scopes or any(scope not in allowed for scope in scopes):
            raise ValueError("Permissões de chave inválidas")
        raw = f"oj_app_{secrets.token_urlsafe(32)}"
        key_id = f"key_{secrets.token_urlsafe(16)}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_app_keys(id, user_id, name, key_prefix, key_hash, scopes_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key_id, user_id, name, raw[:16], _hash_token(raw), json.dumps(scopes), _now()),
            )
        return self.list_app_keys(user_id)[0], raw

    def revoke_app_key(self, user_id: str, key_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE auth_app_keys SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                (_now(), key_id, user_id),
            )
        return result.rowcount == 1


def webauthn_options_to_dict(options: Any) -> dict[str, Any]:
    from webauthn import options_to_json

    return json.loads(options_to_json(options))


__all__ = ["AuthStore", "Principal", "webauthn_options_to_dict"]
