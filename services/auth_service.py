"""Phase A.1: local users, password hashing, roles.

First-run pattern: empty users table means setup mode (auth open).
Once at least one user exists, login is required everywhere.
"""

from werkzeug.security import check_password_hash, generate_password_hash

USER_COLS = ["UserID", "UserName", "PasswordHash", "Role", "Active"]

ROLES = ("admin", "magacioner", "citac")

MIN_PASSWORD_LEN = 8


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)


class AuthService:
    def __init__(self, store):
        self.store = store

    def auth_required(self) -> bool:
        return len(self.store.records()) > 0

    def get(self, username: str):
        return self.store.find("UserName", username)

    def create_user(self, username: str, password: str, role: str = "magacioner"):
        username = (username or "").strip()
        if not username:
            raise ValueError("Корисничкото име е задолжително.")
        if role not in ROLES:
            raise ValueError(f"Невалидна улога: {role}.")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"Лозинката мора да има барем {MIN_PASSWORD_LEN} знаци.")
        if self.get(username) is not None:
            raise ValueError(f"Корисникот {username} веќе постои.")
        self.store.append_row(
            {
                "UserID": username,
                "UserName": username,
                "PasswordHash": hash_password(password),
                "Role": role,
                "Active": "YES",
            }
        )
        return self.get(username)

    def verify(self, username: str, password: str):
        user = self.get((username or "").strip())
        if user is None or user.get("Active") != "YES":
            return None
        if not verify_password(password or "", user.get("PasswordHash", "")):
            return None
        return user

    def set_active(self, username: str, active: bool):
        self.store.update_where(
            "UserName", username, {"Active": "YES" if active else "NO"}
        )

    def set_role(self, username: str, role: str):
        if role not in ROLES:
            raise ValueError(f"Невалидна улога: {role}.")
        self.store.update_where("UserName", username, {"Role": role})

    def change_password(self, username: str, new_password: str):
        if len(new_password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"Лозинката мора да има барем {MIN_PASSWORD_LEN} знаци.")
        self.store.update_where(
            "UserName", username, {"PasswordHash": hash_password(new_password)}
        )

    def list_users(self):
        return self.store.records()
