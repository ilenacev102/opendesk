"""ChatOps: canned response macros administration + macros JSON API."""

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from routes._roles import require
from services import macro_service
from utils.validators import ValidationError

bp = Blueprint("chatops", __name__)


def _bootstrap():
    from app import macros

    return macros


@bp.route("/settings/macros")
@require("admin")
def macros_admin():
    macros = _bootstrap()
    return render_template("macros.html", rows=macro_service.for_picker(macros))


@bp.route("/settings/macros", methods=["POST"])
@require("admin")
def macros_create():
    macros = _bootstrap()
    try:
        row = macro_service.create(
            macros,
            request.form.get("title", ""),
            request.form.get("body", ""),
            category=request.form.get("category", ""),
        )
        flash(f"Макрото „{row['Title']}“ е зачувано.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("chatops.macros_admin"))


@bp.route("/settings/macros/<macro_id>/delete", methods=["POST"])
@require("admin")
def macros_delete(macro_id):
    macros = _bootstrap()
    try:
        row = macro_service.delete(macros, macro_id)
        flash(f"Макрото „{row['Title']}“ е избришано.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("chatops.macros_admin"))


@bp.route("/api/v1/macros")
def api_macros():
    """JSON list of canned macros for the comment picker (any logged-in user)."""
    macros = _bootstrap()
    return jsonify(
        [
            {
                "MacroID": m.get("MacroID", ""),
                "Title": m.get("Title", ""),
                "Category": m.get("Category", ""),
                "BodyText": m.get("BodyText", ""),
            }
            for m in macro_service.for_picker(macros)
        ]
    )
