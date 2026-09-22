"""Shared role guard for blueprints (lazy app import, no cycle)."""

from functools import wraps


def require(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            import app as _app

            return _app.roles_required(*roles)(fn)(*args, **kwargs)

        return wrapper

    return deco
