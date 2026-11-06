"""Preventive Maintenance Scheduler (Flask Blueprint): /maintenance.

Provides automated periodic maintenance tracking for critical IT infrastructure:
- Recurring maintenance schedules (UPS testing, projector filter cleaning, server dusting).
- Next due date automatic calculations based on frequency days.
- Overdue and due-soon status alerts.
- One-click transformation of maintenance orders into IT ServiceDesk incidents.
"""

import datetime as _dt

from flask import Blueprint, flash, redirect, render_template, request, url_for

from utils.validators import ValidationError

bp = Blueprint("maintenance", __name__)


def _parse_days(val, label):
    try:
        n = int(str(val).strip())
        if n < 1:
            raise ValueError()
        return n
    except (ValueError, TypeError):
        raise ValidationError(f"Невалиден интервал за {label}: мора да биде позитивен број денови.")


def _parse_iso(raw, label):
    try:
        return _dt.date.fromisoformat((raw or "").strip()[:10])
    except (ValueError, TypeError):
        raise ValidationError(f"Невалиден датум за {label} (формат YYYY-MM-DD).")


def compute_maint_status(next_due_date, today=None):
    if today is None:
        today = _dt.date.today()
    if isinstance(next_due_date, str):
        try:
            next_due_date = _dt.date.fromisoformat(next_due_date[:10])
        except (ValueError, TypeError):
            return "unknown"
    if next_due_date < today:
        return "overdue"
    if today <= next_due_date <= today + _dt.timedelta(days=14):
        return "due_soon"
    return "ok"


@bp.route("/maintenance", methods=["GET"])
def maintenance_view():
    import app as app_mod

    sched_store = app_mod.maintenance_schedules
    devices = getattr(app_mod, "devices", None)

    records = sched_store.records()
    today = _dt.date.today()

    annotated = []
    overdue_count = 0
    due_soon_count = 0
    ok_count = 0

    for r in records:
        st = compute_maint_status(r.get("NextDue", ""), today)
        if st == "overdue":
            overdue_count += 1
        elif st == "due_soon":
            due_soon_count += 1
        else:
            ok_count += 1

        dev = devices.find("AssetID", r.get("AssetID", "")) if devices else None
        item = dict(r)
        item["calc_status"] = st
        item["device"] = dev
        annotated.append(item)

    # Sort overdue first, then due soon, then ok
    status_order = {"overdue": 0, "due_soon": 1, "ok": 2, "unknown": 3}
    annotated.sort(key=lambda x: (status_order.get(x["calc_status"], 3), x.get("NextDue", "")))

    all_devices = devices.records() if devices else []

    return render_template(
        "maintenance.html",
        schedules=annotated,
        total_count=len(annotated),
        overdue_count=overdue_count,
        due_soon_count=due_soon_count,
        ok_count=ok_count,
        all_devices=all_devices,
        today=today.isoformat(),
    )


@bp.route("/maintenance/new", methods=["POST"])
def maintenance_new():
    import app as app_mod
    import config
    from utils.helpers import next_id

    sched_store = app_mod.maintenance_schedules
    asset_id = request.form.get("asset_id", "").strip()
    title = request.form.get("title", "").strip()
    freq_raw = request.form.get("frequency_days", "90").strip()
    last_serv_raw = request.form.get("last_serviced", "").strip() or _dt.date.today().isoformat()
    notes = request.form.get("notes", "").strip()

    try:
        if not asset_id:
            raise ValidationError("Изберете уред за превентивен сервис.")
        if not title:
            raise ValidationError("Насловот на планот за одржување е задолжителен.")

        freq_days = _parse_days(freq_raw, "интервал на сервис")
        last_serv = _parse_iso(last_serv_raw, "последен сервис")
        next_due = last_serv + _dt.timedelta(days=freq_days)

        sid = next_id(sched_store, "ScheduleID", "MNT")
        sched_store.append_row({
            "ScheduleID": sid,
            "AssetID": asset_id,
            "Title": title,
            "FrequencyDays": str(freq_days),
            "LastServiced": last_serv.isoformat(),
            "NextDue": next_due.isoformat(),
            "Status": "active",
            "Notes": notes,
        })

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([sched_store])

        flash(f"Планот за превентивно одржување {sid} ({title}) е успешно креиран. Следен сервис: {next_due}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("maintenance.maintenance_view"))


@bp.route("/maintenance/complete", methods=["POST"])
def maintenance_complete():
    import app as app_mod
    import config

    sched_store = app_mod.maintenance_schedules
    history = getattr(app_mod, "history", None)

    sid = request.form.get("schedule_id", "").strip()
    serv_date_raw = request.form.get("service_date", "").strip() or _dt.date.today().isoformat()
    notes = request.form.get("notes", "").strip()

    try:
        row = sched_store.find("ScheduleID", sid)
        if not row:
            raise ValidationError(f"Планот за одржување {sid} не постои.")

        serv_date = _parse_iso(serv_date_raw, "датум на завршен сервис")
        freq_days = _parse_days(row.get("FrequencyDays", "90"), "интервал")
        next_due = serv_date + _dt.timedelta(days=freq_days)

        sched_store.update_where(
            "ScheduleID",
            sid,
            {
                "LastServiced": serv_date.isoformat(),
                "NextDue": next_due.isoformat(),
                "Notes": notes or row.get("Notes", ""),
            },
        )

        if history:
            history.log(
                "MAINT_COMPLETE",
                row.get("AssetID", ""),
                row.get("LastServiced", ""),
                serv_date.isoformat(),
                "",
                "",
                f"Превентивен сервис: {row.get('Title')} завршен на {serv_date}. Следен: {next_due}.",
                "",
                "admin",
                "",
            )

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([sched_store])

        flash(f"Сервисот за {sid} е евидентиран како завршен. Следниот датум за сервис е {next_due}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("maintenance.maintenance_view"))


@bp.route("/maintenance/create-ticket", methods=["POST"])
def maintenance_create_ticket():
    import app as app_mod
    import config
    from services.incident_service import IncidentService

    sched_store = app_mod.maintenance_schedules
    sid = request.form.get("schedule_id", "").strip()

    try:
        row = sched_store.find("ScheduleID", sid)
        if not row:
            raise ValidationError(f"Планот {sid} не постои.")

        st = compute_maint_status(row.get("NextDue", ""))
        prio = "high" if st == "overdue" else "medium"

        svc = IncidentService(
            app_mod.incidents,
            getattr(app_mod, "history", None),
            db_path=app_mod.PATHS.get("db"),
        )
        iid = svc.create(
            asset_id=row.get("AssetID", ""),
            title=f"[Превентивен Сервис] {row.get('Title')}",
            priority=prio,
            notes=f"Автоматски генериран сервисен тикет од план {sid}. Доспева на {row.get('NextDue')}.",
            performed_by="maintenance-scheduler",
        )

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([app_mod.incidents])

        flash(f"Сервисен инцидент {iid} е успешно креиран за уредот {row.get('AssetID')}.", "success")
    except (ValidationError, ValueError) as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("maintenance.maintenance_view"))
