"""Admin + auth routes (Flask Blueprint).

Shared app-owned names (stores, services) are imported lazily INSIDE each
view function, so they always resolve against the live ``app`` module object.
That keeps test monkeypatching of ``app`` attributes working. (Module-level
``__getattr__`` delegation was tried first and REJECTED: CPython LOAD_GLOBAL
inside function bodies never consults it, so bare globals stayed undefined.)
Flask names are plain top-level imports (no cycle possible).
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("admin", __name__)

log = __import__("logging").getLogger("servicedesk")


def _admin_only(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        import app as _runtime_app

        return _runtime_app.roles_required("admin")(fn)(*args, **kwargs)

    return wrapper


@bp.route("/api-tokens", methods=["GET", "POST"])
@_admin_only
def api_tokens():
    from app import auth_svc, token_svc

    plain = None
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            owner = request.form.get("username", "").strip()
            if auth_svc.get(owner) is None:
                flash(f"ГРЕШКА: корисникот {owner} не постои.", "danger")
            else:
                plain = token_svc.create(
                    owner,
                    request.form.get("name", "").strip(),
                )
                flash(
                    "Токенот е креиран. Копирајте го сега — нема повторно прикажување.",
                    "success",
                )
        elif action == "revoke":
            try:
                tid = request.form.get("token_id", "").strip()
                rows = token_svc.store.filter_eq("TokenID", tid)
                owner = rows[0].get("UserName", "") if rows else ""
                token_svc.revoke(tid, owner)
                flash("Токенот е отповикан.", "success")
            except ValueError as exc:
                flash(f"ГРЕШКА: {exc}", "danger")
    return render_template(
        "api_tokens.html", tokens=token_svc.store.records(), plain=plain
    )


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    from app import auth_svc

    if auth_svc.auth_required():
        return redirect(url_for("admin.login"))
    if request.method == "POST":
        try:
            auth_svc.create_user(
                request.form.get("username", ""),
                request.form.get("password", ""),
                role="admin",
            )
            flash("Администраторот е креиран. Најавете се.", "success")
            return redirect(url_for("admin.login"))
        except ValueError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    from app import AppUser, auth_svc, login_user

    if request.method == "POST":
        user = auth_svc.verify(
            request.form.get("username", ""), request.form.get("password", "")
        )
        if user is None:
            flash("ГРЕШКА: погрешно корисничко име или лозинка.", "danger")
        else:
            login_user(AppUser(user))
            log.info("Login user=%s", user.get("UserName", ""))
            nxt = request.args.get("next") or url_for("system.dashboard")
            return redirect(nxt)
    return render_template("login.html")


@bp.route("/logout")
def logout():
    from app import logout_user

    logout_user()
    return redirect(url_for("admin.login"))


@bp.route("/users", methods=["GET", "POST"])
@_admin_only
def users():
    from app import auth_svc

    if request.method == "POST":
        action = request.form.get("action", "create")
        try:
            if action == "create":
                auth_svc.create_user(
                    request.form.get("username", ""),
                    request.form.get("password", ""),
                    request.form.get("role", "magacioner"),
                )
                flash("Корисникот е креиран.", "success")
            elif action == "deactivate":
                auth_svc.set_active(request.form.get("username", ""), False)
            elif action == "activate":
                auth_svc.set_active(request.form.get("username", ""), True)
            elif action == "role":
                auth_svc.set_role(
                    request.form.get("username", ""),
                    request.form.get("role", "citac"),
                )
        except ValueError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
    return render_template("users.html", users=auth_svc.list_users())
