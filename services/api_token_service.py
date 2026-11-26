"""Phase A.2: API tokens for REST API v1.

Plaintext token is shown once at creation; only its sha256 hash is stored.
"""

import hashlib
import hmac
import secrets
import uuid

from services.schemas import TOKEN_COLS as TOKEN_COLS


def _hash(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _today() -> str:
    import datetime

    return datetime.date.today().isoformat()


class ApiTokenService:
    def __init__(self, store, history=None):
        self.store = store
        self.history = history

    def _tx(self):
        from services.db_service import store_transaction

        return store_transaction(self.store, getattr(self.history, "store", None))

    def _log(
        self, action, token_id, username, name="", performed_by="system", con=None
    ):
        if self.history is None:
            return
        self.history.log(
            action,
            token_id,
            "",
            "",
            username,
            "",
            name,
            "",
            performed_by,
            "",
            con=con,
        )

    def create(self, username: str, name: str = "", *, performed_by="system") -> str:
        plain = secrets.token_urlsafe(32)
        token_id = uuid.uuid4().hex[:12]
        with self._tx() as con:
            self.store.append_row(
                {
                    "TokenID": token_id,
                    "UserName": username,
                    "TokenHash": _hash(plain),
                    "Name": name or "api",
                    "Created": _today(),
                    "Active": "YES",
                },
                con=con,
            )
            self._log(
                "TOKEN_CREATE",
                token_id,
                username,
                name or "api",
                performed_by,
                con=con,
            )
        return plain

    def list(self, username: str):
        return self.store.filter_eq("UserName", username)

    def verify(self, plain: str, auth_svc):
        if not plain:
            return None
        digest = _hash(plain)
        for row in self.store.records():
            if (
                hmac.compare_digest(row.get("TokenHash", ""), digest)
                and row.get("Active") == "YES"
            ):
                user = auth_svc.get(row.get("UserName", ""))
                if user is None or user.get("Active") != "YES":
                    return None
                return user
        return None

    def revoke(self, token_id: str, username: str, *, performed_by="system"):
        with self._tx() as con:
            rows = self.store.filter_eq("TokenID", token_id)
            if not rows:
                raise ValueError(f"Токенот {token_id} не постои.")
            if rows[0].get("UserName") != username:
                raise ValueError("Не може да се отповика туѓ токен.")
            self.store.update_where("TokenID", token_id, {"Active": "NO"}, con=con)
            self._log(
                "TOKEN_REVOKE",
                token_id,
                username,
                rows[0].get("Name", ""),
                performed_by,
                con=con,
            )
