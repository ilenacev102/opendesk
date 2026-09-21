"""Phase A.2: API tokens for REST API v1.

Plaintext token is shown once at creation; only its sha256 hash is stored.
"""

import hashlib
import secrets
import uuid

TOKEN_COLS = ["TokenID", "UserName", "TokenHash", "Name", "Created", "Active"]


def _hash(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _today() -> str:
    import datetime

    return datetime.date.today().isoformat()


class ApiTokenService:
    def __init__(self, store):
        self.store = store

    def create(self, username: str, name: str = "") -> str:
        plain = secrets.token_urlsafe(32)
        self.store.append_row(
            {
                "TokenID": uuid.uuid4().hex[:12],
                "UserName": username,
                "TokenHash": _hash(plain),
                "Name": name or "api",
                "Created": _today(),
                "Active": "YES",
            }
        )
        return plain

    def list(self, username: str):
        return self.store.filter_eq("UserName", username)

    def verify(self, plain: str, auth_svc):
        if not plain:
            return None
        digest = _hash(plain)
        for row in self.store.records():
            if row.get("TokenHash") == digest and row.get("Active") == "YES":
                user = auth_svc.get(row.get("UserName", ""))
                if user is None or user.get("Active") != "YES":
                    return None
                return user
        return None

    def revoke(self, token_id: str, username: str):
        rows = self.store.filter_eq("TokenID", token_id)
        if not rows:
            raise ValueError(f"Токенот {token_id} не постои.")
        if rows[0].get("UserName") != username:
            raise ValueError("Не може да се отповика туѓ токен.")
        self.store.update_where("TokenID", token_id, {"Active": "NO"})
