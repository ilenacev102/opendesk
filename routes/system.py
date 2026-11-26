"""System routes (Flask Blueprint): dashboard, search, history, health.

App-owned names are imported lazily INSIDE each view so they always resolve
against the live ``app`` module (test monkeypatching keeps working).
"""

from collections import Counter

from flask import Blueprint, redirect, render_template, request, url_for

from routes._roles import require

bp = Blueprint("system", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/health")
def health():
    return {"status": "ok"}, 200


@bp.route("/system/observability")
@require("admin")
def observability_view():
    """Read-only per-process snapshot: 5xx/429 per route and estimated p95."""
    from services.observability import snapshot

    return render_template("observability.html", snap=snapshot())


@bp.route("/")
def dashboard():
    import datetime

    from app import (
        devices,
        employees,
        history,
        incidents,
        licenses,
        warranty_days,
        warranty_level,
    )
    from services import analytics_service as analytics

    devs = devices.records()
    active_emps = employees.filter_eq("Active", "YES")
    counts = dict(Counter(r.get("Status", "") for r in devs)) if devs else {}
    monthly = {}
    for h in history.recent(1000):
        month = (h.get("DateTime", "") or "")[:7]
        if month:
            monthly[month] = monthly.get(month, 0) + 1
    warranties = []
    for d in devs:
        days = warranty_days(d.get("WarrantyUntil", ""))
        if days is not None and days <= 90:
            level, text = warranty_level(days)
            warranties.append(
                {
                    "AssetID": d.get("AssetID", ""),
                    "Model": f"{d.get('Manufacturer', '')} {d.get('Model', '')}",
                    "Days": days,
                    "Level": level,
                    "Text": text,
                }
            )
    warranties.sort(key=lambda x: (x["Days"] is None, x["Days"]))
    attention_devs = [
        {
            "AssetID": d.get("AssetID", ""),
            "Model": f"{d.get('Manufacturer', '')} {d.get('Model', '')}",
            "Status": d.get("Status", ""),
            "Holder": d.get("EmployeeID", "") or "—",
        }
        for d in devs
        if d.get("Status") in ("Broken", "Repair", "Lost", "Stolen")
    ]
    stats = {
        "total_devices": len(devs),
        "total_employees": len(active_emps),
        "computers": sum(
            1 for d in devs if d.get("Type", "") in ("Компјутер", "Laptop")
        ),
        "statuses": counts,
        "available": counts.get("Available", 0),
        "assigned": counts.get("Assigned", 0),
        "attention": sum(
            counts.get(s, 0) for s in ("Broken", "Repair", "Lost", "Stolen")
        ),
        "recent": history.recent(8),
        "months": sorted(monthly),
        "mcounts": [monthly[m] for m in sorted(monthly)],
        "warranties": warranties[:8],
        "wcount": len(warranties),
        "attention_devs": attention_devs,
    }
    inc_records = incidents.records()
    inc_status, inc_priority = analytics.incidents_by(inc_records)
    today = datetime.date.today()
    stats.update(
        {
            "inc_status": inc_status,
            "inc_priority": inc_priority,
            "warranty_fc": analytics.warranty_buckets(devs, today),
            "costs_loc": analytics.costs_by(devs, "Location"),
            "mttr": analytics.mttr_hours(inc_records),
            "breach_open": analytics.breach_counts(inc_records, today),
            "lic_expiring": analytics.license_expiry(licenses.records(), today),
        }
    )
    return render_template("dashboard.html", stats=stats)


@bp.route("/dashboard")
def dashboard_alias():
    return redirect(url_for("system.dashboard"))


@bp.route("/search")
def search():
    from app import devices, employees

    q = (request.args.get("q") or "").strip().lower()
    results = {"employees": [], "devices": []}
    if q:
        results["employees"] = [
            r for r in employees.records() if q in " ".join(r.values()).lower()
        ]
        results["devices"] = [
            r for r in devices.records() if q in " ".join(r.values()).lower()
        ]
    return render_template("search.html", q=q, results=results)


@bp.route("/history")
def history_view():
    from app import employees, history

    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    try:
        per = min(200, max(20, int(request.args.get("per", "50"))))
    except ValueError:
        per = 50
    all_rows = history.recent(5000)
    total = len(all_rows)
    total_pages = max(1, (total + per - 1) // per)
    page = min(page, total_pages)
    start = (page - 1) * per
    rows = all_rows[start : start + per]
    emails = {}
    for h in rows:
        eid = h.get("EmployeeID", "")
        if eid and eid not in emails:
            holder_rec = employees.find("EmployeeID", eid)
            emails[eid] = holder_rec.get("Email", "") if holder_rec else ""
    return render_template(
        "history.html",
        rows=rows,
        emails=emails,
        page=page,
        per=per,
        total=total,
        total_pages=total_pages,
    )


@bp.route("/my-work")
def my_work():
    """F1: personal burning-items page (read-only)."""
    from flask_login import current_user as _cu

    from app import devices, history, incidents
    from services.mywork_service import collect

    who = str(getattr(_cu, "id", "")) if _cu else ""
    data = collect(who, incidents.records(), devices.records(), history.store.records())
    return render_template("mywork.html", who=who, **data)


@bp.route("/notifications")
def notifications_list():
    """F2: unread notifications for the current user."""
    from flask_login import current_user as _cu

    from app import notifications
    from services.notify_center import unread

    who = str(getattr(_cu, "id", "")) if _cu else ""
    return render_template("notifications.html", rows=unread(notifications, who))


@bp.route("/notifications/read", methods=["POST"])
def notifications_read():
    """F2: mark one (or all) notifications as read."""
    from flask import redirect as _redirect
    from flask import request as _request
    from flask import url_for as _url_for
    from flask_login import current_user as _cu

    from app import notifications
    from services.notify_center import mark_read

    who = str(getattr(_cu, "id", "")) if _cu else ""
    mark_read(notifications, who, _request.form.get("notif_id", ""))
    return _redirect(_url_for("system.notifications_list"))


@bp.route("/set-language/<locale>")
def set_language(locale):
    """Switch active locale (en / mk) and redirect back."""
    from flask import redirect as _redirect
    from flask import request as _request
    from services.i18n import set_current_locale

    set_current_locale(locale)
    next_url = _request.referrer or "/"
    resp = _redirect(next_url)
    resp.set_cookie("servicedesk_locale", locale, max_age=30 * 86400, samesite="Lax")
    return resp
