"""Phase A.1: local users, password hashing, roles.

First-run pattern: empty users table means setup mode (auth open).
Once at least one user exists, login is required everywhere.
"""

from werkzeug.security import check_password_hash, generate_password_hash

from services.schemas import USER_COLS as USER_COLS

ROLES = ("admin", "magacioner", "citac")

MIN_PASSWORD_LEN = 8


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


class AuthService:
    def __init__(self, store, history=None):
        self.store = store
        self.history = history

    def _tx(self):
        from services.db_service import store_transaction

        return store_transaction(self.store, getattr(self.history, "store", None))

    def _log(self, action, username, old="", new="", performed_by="system", con=None):
        if self.history is None:
            return
        self.history.log(
            action, username, old, new, "", "", "", "", performed_by, "", con=con
        )

    def auth_required(self) -> bool:
        return len(self.store.records()) > 0

    def get(self, username: str):
        return self.store.find("UserName", username)

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "magacioner",
        *,
        performed_by="system",
    ):
        username = (username or "").strip()
        if not username:
            raise ValueError("Корисничкото име е задолжително.")
        if role not in ROLES:
            raise ValueError(f"Невалидна улога: {role}.")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"Лозинката мора да има барем {MIN_PASSWORD_LEN} знаци.")
        with self._tx() as con:
            if self.get(username) is not None:
                raise ValueError(f"Корисникот {username} веќе постои.")
            self.store.append_row(
                {
                    "UserID": username,
                    "UserName": username,
                    "PasswordHash": hash_password(password),
                    "Role": role,
                    "Active": "YES",
                },
                con=con,
            )
            self._log("USER_CREATE", username, "", role, performed_by, con=con)
        return self.get(username)

    def create_sso_user(
        self,
        username: str,
        email: str = "",
        subject: str = "",
        role: str = "citac",
        *,
        performed_by="system",
    ):
        """Provision a user from SSO (OIDC). Empty PasswordHash means local
        login is impossible — verify() refuses empty hashes."""
        username = (username or "").strip()
        if not username:
            raise ValueError("Корисничкото име е задолжително.")
        if role not in ROLES:
            raise ValueError(f"Невалидна улога: {role}.")
        with self._tx() as con:
            if self.get(username) is not None:
                raise ValueError(f"Корисникот {username} веќе постои.")
            self.store.append_row(
                {
                    "UserID": username,
                    "UserName": username,
                    "PasswordHash": "",
                    "Role": role,
                    "Active": "YES",
                    "Email": (email or "").strip(),
                    "OIDCSubject": (subject or "").strip(),
                },
                con=con,
            )
            self._log("USER_SSO_CREATE", username, "", role, performed_by, con=con)
        return self.get(username)

    def verify(self, username: str, password: str):
        user = self.get((username or "").strip())
        if user is None or user.get("Active") != "YES":
            return None
        if not verify_password(password or "", user.get("PasswordHash", "")):
            return None
        return user

    def set_active(self, username: str, active: bool, *, performed_by="system"):
        new = "YES" if active else "NO"
        with self._tx() as con:
            row = self.get(username)
            old = (row or {}).get("Active", "")
            self.store.update_where("UserName", username, {"Active": new}, con=con)
            self._log(
                "USER_ACTIVATE" if active else "USER_DEACTIVATE",
                username,
                old,
                new,
                performed_by,
                con=con,
            )

    def set_role(self, username: str, role: str, *, performed_by="system"):
        if role not in ROLES:
            raise ValueError(f"Невалидна улога: {role}.")
        with self._tx() as con:
            row = self.get(username)
            old = (row or {}).get("Role", "")
            self.store.update_where("UserName", username, {"Role": role}, con=con)
            self._log("USER_ROLE", username, old, role, performed_by, con=con)

    def change_password(
        self, username: str, new_password: str, *, performed_by="system"
    ):
        if len(new_password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"Лозинката мора да има барем {MIN_PASSWORD_LEN} знаци.")
        with self._tx() as con:
            self.store.update_where(
                "UserName",
                username,
                {"PasswordHash": hash_password(new_password)},
                con=con,
            )
            self._log("USER_PASS", username, "", "changed", performed_by, con=con)

    def link_sso(self, username: str, subject: str, *, performed_by="system"):
        with self._tx() as con:
            row = self.get(username)
            old = (row or {}).get("OIDCSubject", "")
            self.store.update_where(
                "UserName", username, {"OIDCSubject": (subject or "").strip()}, con=con
            )
            self._log(
                "USER_SSO_LINK",
                username,
                old,
                (subject or "").strip(),
                performed_by,
                con=con,
            )

    def list_users(self):
        return self.store.records()
