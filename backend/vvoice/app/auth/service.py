from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import math
import re
import secrets
import sqlite3
import threading
import time
import uuid

from vvoice.core.config import SecuritySettings


PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,80}$")
AUTH_RATE_LIMIT_MAX_ATTEMPTS = 5
AUTH_RATE_LIMIT_WINDOW_SECONDS = 5 * 60


class AuthError(ValueError):
    """Raised when a local auth operation cannot be completed."""


@dataclass(frozen=True)
class Account:
    account_id: str
    username: str
    role: str
    created_at: str


@dataclass(frozen=True)
class CreatedSession:
    token: str
    expires_at: str


class LocalAuthService:
    def __init__(self, settings: SecuritySettings) -> None:
        self.settings = settings
        self.path = settings.auth_db_path
        self._lock = threading.RLock()
        self._login_rate_limiter = _MemoryRateLimiter(
            max_attempts=AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS,
        )
        self._password_change_rate_limiter = _MemoryRateLimiter(
            max_attempts=AUTH_RATE_LIMIT_MAX_ATTEMPTS,
            window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def auth_required(self) -> bool:
        return self.settings.auth_required

    @property
    def setup_required(self) -> bool:
        return self.auth_required and not self.has_accounts()

    def has_accounts(self) -> bool:
        with self._connect() as db:
            row = db.execute("select count(*) as count from accounts").fetchone()
            return int(row["count"]) > 0

    def create_owner(self, username: str, password: str) -> Account:
        normalized_username = _normalize_username(username)
        _validate_password(password)
        with self._lock, self._connect() as db:
            row = db.execute("select count(*) as count from accounts").fetchone()
            if int(row["count"]) > 0:
                raise AuthError("Local owner account already exists.")

            now = _utc_now()
            account = Account(
                account_id=uuid.uuid4().hex,
                username=normalized_username,
                role="owner",
                created_at=now,
            )
            db.execute(
                """
                insert into accounts(account_id, username, password_hash, role, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    account.account_id,
                    account.username,
                    _hash_password(password),
                    account.role,
                    now,
                    now,
                ),
            )
            return account

    def authenticate(self, username: str, password: str) -> Account | None:
        normalized_username = _normalize_username(username)
        with self._connect() as db:
            row = db.execute(
                """
                select account_id, username, password_hash, role, created_at
                from accounts
                where username = ?
                """,
                (normalized_username,),
            ).fetchone()
            if row is None:
                return None

            if not _verify_password(password, str(row["password_hash"])):
                return None

            return _account_from_row(row)

    def record_login_attempt(self, identifier: str) -> int | None:
        return self._login_rate_limiter.record(identifier)

    def clear_login_attempts(self, identifier: str) -> None:
        self._login_rate_limiter.reset(identifier)

    def record_password_change_attempt(self, identifier: str) -> int | None:
        return self._password_change_rate_limiter.record(identifier)

    def clear_password_change_attempts(self, identifier: str) -> None:
        self._password_change_rate_limiter.reset(identifier)

    def create_session(self, account: Account, user_agent: str | None = None) -> CreatedSession:
        token = secrets.token_urlsafe(40)
        now = _utc_datetime()
        expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
        with self._lock, self._connect() as db:
            db.execute(
                """
                insert into sessions(
                    session_id,
                    account_id,
                    token_hash,
                    created_at,
                    last_seen_at,
                    expires_at,
                    revoked_at,
                    user_agent
                )
                values (?, ?, ?, ?, ?, ?, null, ?)
                """,
                (
                    uuid.uuid4().hex,
                    account.account_id,
                    self._hash_session_token(token),
                    _format_datetime(now),
                    _format_datetime(now),
                    _format_datetime(expires_at),
                    (user_agent or "")[:512],
                ),
            )
        return CreatedSession(token=token, expires_at=_format_datetime(expires_at))

    def account_from_session_token(self, token: str | None) -> Account | None:
        if not token:
            return None

        token_hash = self._hash_session_token(token)
        now = _utc_datetime()
        with self._lock, self._connect() as db:
            row = db.execute(
                """
                select
                    sessions.session_id,
                    sessions.expires_at,
                    accounts.account_id,
                    accounts.username,
                    accounts.role,
                    accounts.created_at
                from sessions
                join accounts on accounts.account_id = sessions.account_id
                where sessions.token_hash = ?
                  and sessions.revoked_at is null
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None

            expires_at = _parse_datetime(str(row["expires_at"]))
            if expires_at <= now:
                db.execute(
                    "update sessions set revoked_at = ? where session_id = ?",
                    (_format_datetime(now), row["session_id"]),
                )
                return None

            db.execute(
                "update sessions set last_seen_at = ? where session_id = ?",
                (_format_datetime(now), row["session_id"]),
            )
            return _account_from_row(row)

    def revoke_session(self, token: str | None) -> bool:
        if not token:
            return False

        with self._lock, self._connect() as db:
            cursor = db.execute(
                """
                update sessions
                set revoked_at = ?
                where token_hash = ?
                  and revoked_at is null
                """,
                (_utc_now(), self._hash_session_token(token)),
            )
            return cursor.rowcount > 0

    def change_password(
        self,
        account_id: str,
        current_password: str,
        new_password: str,
        current_session_token: str | None,
    ) -> int:
        _validate_password(new_password)
        current_token_hash = (
            self._hash_session_token(current_session_token) if current_session_token else None
        )
        now = _utc_now()

        with self._lock, self._connect() as db:
            row = db.execute(
                """
                select account_id, password_hash
                from accounts
                where account_id = ?
                """,
                (account_id,),
            ).fetchone()
            if row is None:
                raise AuthError("Local account was not found.")

            password_hash = str(row["password_hash"])
            if not _verify_password(current_password, password_hash):
                raise AuthError("Current password is incorrect.")
            if _verify_password(new_password, password_hash):
                raise AuthError("New password must be different.")

            db.execute(
                """
                update accounts
                set password_hash = ?, updated_at = ?
                where account_id = ?
                """,
                (_hash_password(new_password), now, account_id),
            )

            if current_token_hash:
                cursor = db.execute(
                    """
                    update sessions
                    set revoked_at = ?
                    where account_id = ?
                      and token_hash != ?
                      and revoked_at is null
                    """,
                    (now, account_id, current_token_hash),
                )
            else:
                cursor = db.execute(
                    """
                    update sessions
                    set revoked_at = ?
                    where account_id = ?
                      and revoked_at is null
                    """,
                    (now, account_id),
                )

            return cursor.rowcount

    def _hash_session_token(self, token: str) -> str:
        secret = self.settings.session_secret.encode("utf-8")
        if secret:
            digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).digest()
        else:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                create table if not exists accounts (
                    account_id text primary key,
                    username text not null unique,
                    password_hash text not null,
                    role text not null,
                    created_at text not null,
                    updated_at text not null
                )
                """,
            )
            db.execute(
                """
                create table if not exists sessions (
                    session_id text primary key,
                    account_id text not null,
                    token_hash text not null unique,
                    created_at text not null,
                    last_seen_at text not null,
                    expires_at text not null,
                    revoked_at text,
                    user_agent text not null default '',
                    foreign key(account_id) references accounts(account_id)
                )
                """,
            )
            db.execute(
                "create index if not exists idx_sessions_token_hash on sessions(token_hash)",
            )
            db.execute(
                "create index if not exists idx_sessions_account_id on sessions(account_id)",
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class _MemoryRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    def record(self, identifier: str) -> int | None:
        now = time.monotonic()
        with self._lock:
            attempts = self._active_attempts(identifier, now)
            if len(attempts) >= self.max_attempts:
                self._attempts[identifier] = attempts
                retry_after = self.window_seconds - (now - attempts[0])
                return max(1, math.ceil(retry_after))

            attempts.append(now)
            self._attempts[identifier] = attempts
            return None

    def reset(self, identifier: str) -> None:
        with self._lock:
            self._attempts.pop(identifier, None)

    def _active_attempts(self, identifier: str, now: float) -> list[float]:
        return [
            attempt
            for attempt in self._attempts.get(identifier, [])
            if now - attempt < self.window_seconds
        ]


def _normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.match(normalized):
        raise AuthError(
            "Username must be 3-80 characters and use letters, numbers, dot, underscore, hyphen, or @.",
        )
    return normalized


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")
    if len(password) > 512:
        raise AuthError("Password is too long.")


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return "$".join(
        [
            PBKDF2_ALGORITHM,
            str(PBKDF2_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ],
    )


def _verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded_hash.split("$", 3)
        if algorithm != PBKDF2_ALGORITHM:
            return False
        salt_bytes = _b64decode(salt)
        expected_bytes = _b64decode(expected)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt_bytes,
            int(iterations),
        )
        return hmac.compare_digest(candidate, expected_bytes)
    except (ValueError, TypeError):
        return False


def _account_from_row(row: sqlite3.Row) -> Account:
    return Account(
        account_id=str(row["account_id"]),
        username=str(row["username"]),
        role=str(row["role"]),
        created_at=str(row["created_at"]),
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _utc_datetime() -> datetime:
    return datetime.now(UTC)


def _utc_now() -> str:
    return _format_datetime(_utc_datetime())


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
