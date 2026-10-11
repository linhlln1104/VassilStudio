"""SQLite-backed named service identities, revocable keys and actor audit.

Mixed into LocalAuthService so auth metadata remains in its existing database.
Random API tokens are hashed independently of the session signing secret.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
import sqlite3
import uuid

from vvoice.shared.security.principal import ALL_SCOPES, ROLE_SCOPES, Principal


class IamError(ValueError):
    pass


class IamService:
    def _ensure_iam_schema(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript("""
                create table if not exists service_principals (
                    principal_id text primary key, name text not null unique,
                    role text not null, scopes_json text not null,
                    created_at text not null, disabled_at text
                );
                create table if not exists api_keys (
                    key_id text primary key, principal_id text not null,
                    name text not null, prefix text not null, token_hash text not null unique,
                    created_at text not null, expires_at text, revoked_at text, last_used_at text,
                    foreign key(principal_id) references service_principals(principal_id)
                );
                create index if not exists idx_api_keys_principal on api_keys(principal_id);
                create table if not exists service_sessions (
                    session_id text primary key, principal_id text not null, key_id text not null,
                    token_hash text not null unique, created_at text not null, expires_at text not null,
                    revoked_at text, foreign key(principal_id) references service_principals(principal_id),
                    foreign key(key_id) references api_keys(key_id)
                );
                create table if not exists audit_events (
                    event_id integer primary key autoincrement, created_at text not null,
                    actor_id text, actor_name text, actor_kind text, action text not null,
                    resource_type text not null, resource_id text not null,
                    request_id text, details_json text not null
                );
                create index if not exists idx_audit_actor on audit_events(actor_id, event_id);
            """)

    def list_service_accounts(self) -> list[dict]:
        with self._connect() as db:
            return [_service_account(row) for row in db.execute(
                "select * from service_principals order by created_at, principal_id",
            )]

    def create_service_account(self, name: str, role: str, scopes: list[str] | None = None) -> dict:
        name = _name(name)
        if role not in ROLE_SCOPES or role == "owner":
            raise IamError("Choose admin, operator, editor, or reviewer role.")
        allowed = ROLE_SCOPES[role]
        selected = allowed if scopes is None else frozenset(scopes)
        if not selected or not selected <= (ALL_SCOPES | {"*"}):
            raise IamError("Scopes must contain known, nonempty permissions.")
        if "*" not in allowed and not selected <= allowed:
            raise IamError("Requested scopes exceed the role permissions.")
        record = {"principal_id": uuid.uuid4().hex, "name": name, "role": role,
                  "scopes": sorted(selected), "created_at": _now(), "disabled_at": None}
        try:
            with self._lock, self._connect() as db:
                db.execute("insert into service_principals values (?, ?, ?, ?, ?, null)", (
                    record["principal_id"], name, role, json.dumps(record["scopes"]), record["created_at"],
                ))
        except sqlite3.IntegrityError as exc:
            raise IamError("A service account with this name already exists.") from exc
        return record

    def disable_service_account(self, principal_id: str) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute("select * from service_principals where principal_id = ?", (principal_id,)).fetchone()
            if row is None:
                raise IamError("Service account was not found.")
            now = row["disabled_at"] or _now()
            db.execute("update service_principals set disabled_at = ? where principal_id = ?", (now, principal_id))
            db.execute("update api_keys set revoked_at = ? where principal_id = ? and revoked_at is null", (now, principal_id))
            result = _service_account(row)
            result["disabled_at"] = now
            return result

    def list_api_keys(self) -> list[dict]:
        with self._connect() as db:
            return [_key(row) for row in db.execute("select * from api_keys order by created_at desc, key_id")]

    def has_active_api_keys(self) -> bool:
        with self._connect() as db:
            return db.execute("""select 1 from api_keys k join service_principals p
                on p.principal_id = k.principal_id where k.revoked_at is null
                and p.disabled_at is null and (k.expires_at is null or k.expires_at > ?) limit 1""", (_now(),)).fetchone() is not None

    def create_api_key(self, principal_id: str, name: str, expires_at: str | None = None) -> dict:
        name = _name(name)
        if expires_at:
            try:
                expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if expiration.tzinfo is None or expiration <= datetime.now(UTC):
                    raise ValueError
                expires_at = expiration.astimezone(UTC).isoformat().replace("+00:00", "Z")
            except ValueError as exc:
                raise IamError("Key expiry must be a future timestamp with timezone.") from exc
        key_id = uuid.uuid4().hex
        token = f"vsk_{key_id}_{secrets.token_urlsafe(32)}"
        record = {"key_id": key_id, "principal_id": principal_id, "name": name,
                  "prefix": token[:16], "created_at": _now(), "expires_at": expires_at,
                  "revoked_at": None, "last_used_at": None}
        with self._lock, self._connect() as db:
            account = db.execute("select disabled_at from service_principals where principal_id = ?", (principal_id,)).fetchone()
            if account is None or account["disabled_at"] is not None:
                raise IamError("Active service account was not found.")
            db.execute("""insert into api_keys(key_id, principal_id, name, prefix, token_hash,
                created_at, expires_at) values (?, ?, ?, ?, ?, ?, ?)""", (
                key_id, principal_id, name, record["prefix"], _token_hash(token), record["created_at"], expires_at,
            ))
        return {"key": record, "token": token}

    def revoke_api_key(self, key_id: str) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("select key_id from api_keys where key_id = ?", (key_id,)).fetchone()
            if row is None:
                raise IamError("API key was not found.")
            db.execute("update api_keys set revoked_at = coalesce(revoked_at, ?) where key_id = ?", (_now(), key_id))
            return True

    def principal_from_api_key(self, token: str | None) -> Principal | None:
        if not token or not token.startswith("vsk_") or len(token) > 256:
            return None
        with self._lock, self._connect() as db:
            row = db.execute("""select p.*, k.key_id from api_keys k join service_principals p
                on p.principal_id = k.principal_id where k.token_hash = ?
                and k.revoked_at is null and p.disabled_at is null
                and (k.expires_at is null or k.expires_at > ?)""", (_token_hash(token), _now())).fetchone()
            if row is None:
                return None
            db.execute("update api_keys set last_used_at = ? where key_id = ?", (_now(), row["key_id"]))
            return Principal(str(row["principal_id"]), str(row["name"]), "service", str(row["role"]), tuple(json.loads(row["scopes_json"])))

    def record_audit(self, actor: Principal | None, action: str, resource_type: str = "",
                     resource_id: str = "", request_id: str | None = None, details: dict | None = None) -> None:
        # Callers supply structured metadata only: never request bodies, audio, or credentials.
        with self._lock, self._connect() as db:
            db.execute("""insert into audit_events(created_at, actor_id, actor_name, actor_kind,
                action, resource_type, resource_id, request_id, details_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                _now(), actor.principal_id if actor else None, actor.name if actor else None,
                actor.kind if actor else None, action, resource_type, resource_id, request_id,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            ))

    def create_key_session(self, api_key: str) -> dict | None:
        """Exchange a valid key for a cookie token that remains bound to its revocation."""
        principal = self.principal_from_api_key(api_key)
        if principal is None:
            return None
        token = secrets.token_urlsafe(40)
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self.settings.session_ttl_seconds)
        with self._lock, self._connect() as db:
            key = db.execute("select key_id, expires_at, revoked_at from api_keys where token_hash = ?", (_token_hash(api_key),)).fetchone()
            if key is None or key["revoked_at"] is not None:
                return None
            if key["expires_at"]:
                expires = min(expires, datetime.fromisoformat(key["expires_at"].replace("Z", "+00:00")))
            expires_at = expires.isoformat().replace("+00:00", "Z")
            db.execute("""insert into service_sessions(session_id, principal_id, key_id, token_hash,
                created_at, expires_at) values (?, ?, ?, ?, ?, ?)""", (
                uuid.uuid4().hex, principal.principal_id, key["key_id"], _token_hash(token), _now(), expires_at,
            ))
        return {"token": token, "expires_at": expires_at, "principal": principal}

    def principal_from_key_session(self, token: str | None) -> Principal | None:
        if not token or len(token) > 256:
            return None
        with self._connect() as db:
            row = db.execute("""select p.* from service_sessions s
                join api_keys k on k.key_id = s.key_id
                join service_principals p on p.principal_id = s.principal_id
                where s.token_hash = ? and s.revoked_at is null and s.expires_at > ?
                and k.revoked_at is null and (k.expires_at is null or k.expires_at > ?)
                and p.disabled_at is null""", (_token_hash(token), _now(), _now())).fetchone()
            if row is None:
                return None
            return Principal(str(row["principal_id"]), str(row["name"]), "service", str(row["role"]), tuple(json.loads(row["scopes_json"])))

    def revoke_key_session(self, token: str | None) -> None:
        if token:
            with self._lock, self._connect() as db:
                db.execute("update service_sessions set revoked_at = ? where token_hash = ? and revoked_at is null",
                           (_now(), _token_hash(token)))

    def list_audit(self, limit: int = 100, offset: int = 0, actor_id: str | None = None) -> list[dict]:
        if not 1 <= limit <= 500 or offset < 0:
            raise IamError("Audit pagination is invalid.")
        query = "select * from audit_events"
        values: list = []
        if actor_id is not None:
            query += " where actor_id = ?"
            values.append(actor_id)
        query += " order by event_id desc limit ? offset ?"
        values.extend((limit, offset))
        with self._connect() as db:
            events = [dict(row) for row in db.execute(query, values)]
        for event in events:
            event["details"] = json.loads(event.pop("details_json"))
        return events


def _name(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 120 or any(ord(char) < 32 for char in value):
        raise IamError("Name must contain 1-120 printable characters.")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _service_account(row) -> dict:
    result = dict(row)
    result["scopes"] = json.loads(result.pop("scopes_json"))
    return result


def _key(row) -> dict:
    return {key: row[key] for key in ("key_id", "principal_id", "name", "prefix", "created_at", "expires_at", "revoked_at", "last_used_at")}
