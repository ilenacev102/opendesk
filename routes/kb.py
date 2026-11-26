"""Knowledge base routes (Flask Blueprint): list/search/detail/create/edit.

App-owned names are imported lazily INSIDE each view function, so they
always resolve against the live ``app`` module object.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from routes._roles import require
from utils.validators import ValidationError

bp = Blueprint("kb", __name__)

log = __import__("logging").getLogger("servicedesk")


def _search(rows, q):
    words = (q or "").strip().lower().split()
    if not words:
        return rows
    out = []
    for r in rows:
        haystack = " ".join(
            [r.get("Title", ""), r.get("Body", ""), r.get("Tags", "")]
        ).lower()
        if all(w in haystack for w in words):
            out.append(r)
    return out


@bp.route("/kb")
def kb_list():
    from app import kb_articles, kb_ratings
    from services import kb_rating

    q = request.args.get("q", "")
    rows = _search(kb_articles.records(), q)
    rows.sort(key=lambda r: r.get("Updated", ""), reverse=True)
    rows = kb_rating.ranked(rows, kb_ratings)
    return render_template("kb.html", rows=rows, q=q)


@bp.route("/kb/<aid>")
def kb_detail(aid):
    from flask_login import current_user as _cu

    from app import kb_articles, kb_ratings
    from services import kb_rating

    art = kb_articles.find("ArticleID", aid)
    if art is None:
        abort(404)
    avg = kb_rating.average(kb_ratings, aid)
    who = str(getattr(_cu, "id", "")) if _cu else ""
    my_score = None
    if who:
        for r in kb_ratings.records():
            if r.get("ArticleID") == aid and r.get("UserName") == who:
                try:
                    my_score = int(r.get("Score", ""))
                except (TypeError, ValueError):
                    my_score = None
                break
    return render_template("kb_article.html", art=art, avg=avg, my_score=my_score)


@bp.route("/kb/new", methods=["POST"])
@require("admin", "magacioner")
def kb_new():
    import config
    from app import backup_all, kb_articles
    from utils.helpers import next_id, stamp

    title = request.form.get("Title", "").strip()
    body = request.form.get("Body", "").strip()
    if not title or not body:
        flash("ГРЕШКА: насловот и текстот се задолжителни.", "danger")
        return redirect(url_for("kb.kb_list"))
    aid = next_id(kb_articles, "ArticleID", "KB")
    now = stamp()
    kb_articles.append_row(
        {
            "ArticleID": aid,
            "Title": title,
            "Body": body,
            "Tags": request.form.get("Tags", "").strip(),
            "Created": now,
            "Updated": now,
        }
    )
    if config.BACKUP_ON_WRITE:
        backup_all([kb_articles])
    flash(f"Написот {aid} е креиран.", "success")
    return redirect(url_for("kb.kb_detail", aid=aid))


@bp.route("/kb/<aid>/edit", methods=["POST"])
@require("admin", "magacioner")
def kb_edit(aid):
    import config
    from app import backup_all, kb_articles
    from utils.helpers import stamp

    if kb_articles.find("ArticleID", aid) is None:
        abort(404)
    title = request.form.get("Title", "").strip()
    body = request.form.get("Body", "").strip()
    if not title or not body:
        flash("ГРЕШКА: насловот и текстот се задолжителни.", "danger")
        return redirect(url_for("kb.kb_detail", aid=aid))
    kb_articles.update_where(
        "ArticleID",
        aid,
        {
            "Title": title,
            "Body": body,
            "Tags": request.form.get("Tags", "").strip(),
            "Updated": stamp(),
        },
    )
    if config.BACKUP_ON_WRITE:
        backup_all([kb_articles])
    flash(f"Написот {aid} е ажуриран.", "success")
    return redirect(url_for("kb.kb_detail", aid=aid))


@bp.route("/kb/<aid>/rate", methods=["POST"])
@require("admin", "magacioner")
def kb_rate(aid):
    from flask_login import current_user as _cu

    import config
    from app import backup_all, history, kb_articles, kb_ratings
    from services import kb_rating

    if kb_articles.find("ArticleID", aid) is None:
        abort(404)
    who = str(getattr(_cu, "id", "")) if _cu else ""
    try:
        kb_rating.vote(
            kb_ratings, aid, who, request.form.get("score", ""), history=history
        )
        if config.BACKUP_ON_WRITE:
            backup_all([kb_ratings])
        flash("Оцената е запишана.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")
    return redirect(url_for("kb.kb_detail", aid=aid))
