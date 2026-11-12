"""ITIL / ITSM Powerhouse (Flask Blueprint): /problems & /changes.

Implements ServiceNow / Jira Service Management standard ITIL practices:
- Problem Management (PRB-XXXXXX): Grouping multiple incidents, identifying root causes,
  and executing cascading resolution to auto-close all linked incidents with a single action.
- Change Advisory Board & Change Requests (CHG-XXXXXX): Risk assessments, rollback plans,
  maintenance windows, and CAB approvals.
- Multi-Stage Request Approvals: Tiered approval workflow (Manager -> IT).
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from utils.validators import ValidationError

bp = Blueprint("itsm", __name__)


def _current_who():
    if current_user and getattr(current_user, "is_authenticated", False):
        return str(getattr(current_user, "id", "")).strip() or "admin"
    return "admin"


# ==========================================
# 1. PROBLEM MANAGEMENT (PRB-XXXXXX)
# ==========================================


@bp.route("/problems", methods=["GET"])
def problems_view():
    import app as app_mod

    problems_store = app_mod.problems
    incidents_store = getattr(app_mod, "incidents", None)

    all_problems = problems_store.records()
    all_incidents = incidents_store.records() if incidents_store else []

    # Map linked incidents per problem
    incidents_by_prob = {}
    for inc in all_incidents:
        linked = (inc.get("LinkedTo") or "").strip()
        if linked.startswith("PRB-"):
            incidents_by_prob.setdefault(linked, []).append(inc)

    open_incidents = [
        i for i in all_incidents if i.get("Status") not in ("closed", "resolved")
    ]

    annotated = []
    open_count = 0
    resolved_count = 0

    for prob in all_problems:
        pid = prob.get("ProblemID", "")
        linked_incs = incidents_by_prob.get(pid, [])
        st = prob.get("Status", "open")
        if st in ("resolved", "closed"):
            resolved_count += 1
        else:
            open_count += 1

        p_copy = dict(prob)
        p_copy["linked_incidents"] = linked_incs
        p_copy["linked_count"] = len(linked_incs)
        annotated.append(p_copy)

    # Sort open first, then resolved
    annotated.sort(
        key=lambda x: (
            1 if x.get("Status") in ("resolved", "closed") else 0,
            x.get("Created", ""),
        ),
        reverse=True,
    )

    return render_template(
        "problems.html",
        problems=annotated,
        total_count=len(annotated),
        open_count=open_count,
        resolved_count=resolved_count,
        open_incidents=open_incidents,
    )


@bp.route("/problems/new", methods=["POST"])
def problems_new():
    import app as app_mod
    import config
    from utils.helpers import next_id, stamp

    problems_store = app_mod.problems
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    workaround = request.form.get("workaround", "").strip()
    owner = request.form.get("owner", "").strip() or _current_who()

    try:
        if not title:
            raise ValidationError("Насловот на проблемот е задолжителен.")

        pid = next_id(problems_store, "ProblemID", "PRB-")
        problems_store.append_row(
            {
                "ProblemID": pid,
                "Title": title,
                "Description": description,
                "RootCause": "",
                "Workaround": workaround,
                "Status": "investigating",
                "Owner": owner,
                "Created": stamp(),
                "ResolvedAt": "",
            }
        )

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([problems_store])

        flash(f"Проблемот {pid} ({title}) е успешно отворен за истрага.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("itsm.problems_view"))


@bp.route("/problems/link-incident", methods=["POST"])
def problems_link_incident():
    import app as app_mod
    import config

    incidents_store = getattr(app_mod, "incidents", None)
    pid = request.form.get("problem_id", "").strip()
    iid = request.form.get("incident_id", "").strip()

    try:
        if not pid or not iid:
            raise ValidationError("Изберете проблем и инцидент за поврзување.")
        if not incidents_store:
            raise ValidationError("Складиштето за инциденти е недостапно.")
        inc = incidents_store.find("IncidentID", iid)
        if not inc:
            raise ValidationError(f"Инцидентот {iid} не постои.")

        incidents_store.update_where("IncidentID", iid, {"LinkedTo": pid})

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([incidents_store])

        flash(f"Инцидентот {iid} е успешно поврзан со проблемот {pid}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("itsm.problems_view"))


@bp.route("/problems/resolve", methods=["POST"])
def problems_resolve():
    """Resolves the problem and cascades resolution to all linked incidents."""
    import app as app_mod
    import config
    from utils.helpers import stamp

    problems_store = app_mod.problems
    incidents_store = getattr(app_mod, "incidents", None)
    history = getattr(app_mod, "history", None)

    pid = request.form.get("problem_id", "").strip()
    root_cause = request.form.get("root_cause", "").strip()
    workaround = request.form.get("workaround", "").strip()
    who = _current_who()

    try:
        if not pid:
            raise ValidationError("ID на проблем е задолжителен.")
        prob = problems_store.find("ProblemID", pid)
        if not prob:
            raise ValidationError(f"Проблемот {pid} не постои.")
        if not root_cause:
            raise ValidationError(
                "Внесувањето на Root Cause (Основна причина) е задолжително за затворање на Проблем."
            )

        now_str = stamp()
        problems_store.update_where(
            "ProblemID",
            pid,
            {
                "RootCause": root_cause,
                "Workaround": workaround or prob.get("Workaround", ""),
                "Status": "resolved",
                "ResolvedAt": now_str,
            },
        )

        # Cascading resolution on all linked incidents
        cascaded_count = 0
        if incidents_store:
            for inc in incidents_store.records():
                if (inc.get("LinkedTo") or "").strip() == pid and inc.get(
                    "Status"
                ) not in ("closed", "resolved"):
                    old_notes = inc.get("Notes", "")
                    resolution_note = f"[Решено преку Проблем {pid}]: {root_cause}"
                    new_notes = (
                        f"{old_notes}\n{resolution_note}".strip()
                        if old_notes
                        else resolution_note
                    )
                    incidents_store.update_where(
                        "IncidentID",
                        inc["IncidentID"],
                        {
                            "Status": "closed",
                            "ClosedAt": now_str,
                            "Notes": new_notes,
                        },
                    )
                    if history:
                        history.log(
                            "INC_RESOLVE",
                            inc["IncidentID"],
                            inc.get("Status", ""),
                            "closed",
                            "",
                            "",
                            resolution_note,
                            "",
                            who,
                            "",
                        )
                    cascaded_count += 1

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            stores_to_backup = [problems_store]
            if incidents_store:
                stores_to_backup.append(incidents_store)
            app_mod.backup_all(stores_to_backup)

        from app import webhooks as webhooks_store
        from services import webhook_service

        webhook_service.dispatch(
            webhooks_store,
            "problem.resolved",
            {
                "ProblemID": pid,
                "RootCause": root_cause,
                "Workaround": workaround,
                "CascadedIncidents": cascaded_count,
            },
        )

        flash(
            f"Проблемот {pid} е означен како решен! Автоматски се затворени {cascaded_count} поврзани инциденти.",
            "success",
        )
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("itsm.problems_view"))


# ==========================================
# 2. CHANGE ADVISORY BOARD & CHANGES (CHG)
# ==========================================


@bp.route("/changes", methods=["GET"])
def changes_view():
    import app as app_mod

    changes_store = app_mod.changes
    all_changes = changes_store.records()

    pending_cab_count = sum(1 for c in all_changes if c.get("Status") == "pending_cab")
    approved_count = sum(1 for c in all_changes if c.get("Status") == "approved")
    implemented_count = sum(1 for c in all_changes if c.get("Status") == "implemented")
    high_risk_count = sum(
        1 for c in all_changes if c.get("RiskLevel") in ("high", "critical")
    )

    # Order: pending CAB first, then approved, then others
    status_weights = {
        "pending_cab": 0,
        "approved": 1,
        "implemented": 2,
        "rejected": 3,
        "failed": 4,
    }
    ordered = sorted(
        all_changes,
        key=lambda c: (status_weights.get(c.get("Status"), 5), c.get("Created", "")),
        reverse=True,
    )

    return render_template(
        "changes.html",
        changes=ordered,
        total_count=len(all_changes),
        pending_cab_count=pending_cab_count,
        approved_count=approved_count,
        implemented_count=implemented_count,
        high_risk_count=high_risk_count,
    )


@bp.route("/changes/new", methods=["POST"])
def changes_new():
    import app as app_mod
    import config
    from utils.helpers import next_id, stamp

    changes_store = app_mod.changes
    title = request.form.get("title", "").strip()
    risk_level = request.form.get("risk_level", "medium").strip()
    impact_scope = request.form.get("impact_scope", "").strip()
    sched_start = request.form.get("scheduled_start", "").strip()
    sched_end = request.form.get("scheduled_end", "").strip()
    rollback_plan = request.form.get("rollback_plan", "").strip()
    requester = _current_who()

    try:
        if not title:
            raise ValidationError("Насловот на барањето за промена е задолжителен.")
        if not rollback_plan:
            raise ValidationError(
                "Rollback планот е задолжителен според ITIL стандардот пред одобрување од CAB."
            )

        cid = next_id(changes_store, "ChangeID", "CHG-")
        changes_store.append_row(
            {
                "ChangeID": cid,
                "Title": title,
                "RiskLevel": risk_level,
                "ImpactScope": impact_scope,
                "ScheduledStart": sched_start,
                "ScheduledEnd": sched_end,
                "RollbackPlan": rollback_plan,
                "Status": "pending_cab",
                "Requester": requester,
                "ApprovedBy": "",
                "Created": stamp(),
            }
        )

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([changes_store])

        from app import webhooks as webhooks_store
        from services import webhook_service

        webhook_service.dispatch(
            webhooks_store,
            "change.cab_pending",
            {
                "ChangeID": cid,
                "Title": title,
                "Status": "pending_cab",
                "Requester": requester,
            },
        )

        flash(
            f"Барањето за промена {cid} ({title}) е поднесено до CAB за одобрување.",
            "success",
        )
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("itsm.changes_view"))


@bp.route("/changes/decision", methods=["POST"])
def changes_decision():
    """CAB Decision: approve or reject."""
    import app as app_mod
    import config

    changes_store = app_mod.changes
    cid = request.form.get("change_id", "").strip()
    decision = request.form.get("decision", "").strip().lower()
    who = _current_who()

    try:
        chg = changes_store.find("ChangeID", cid)
        if not chg:
            raise ValidationError(f"Промената {cid} не постои.")

        new_status = "approved" if decision == "approve" else "rejected"
        changes_store.update_where(
            "ChangeID",
            cid,
            {
                "Status": new_status,
                "ApprovedBy": who,
            },
        )

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([changes_store])

        action_label = (
            "одобрена од CAB" if new_status == "approved" else "одбиена од CAB"
        )
        flash(f"Промената {cid} е {action_label}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("itsm.changes_view"))


@bp.route("/changes/implement", methods=["POST"])
def changes_implement():
    """Marks a change as successfully implemented or failed/rolled back."""
    import app as app_mod
    import config

    changes_store = app_mod.changes
    cid = request.form.get("change_id", "").strip()
    result = request.form.get("result", "implemented").strip().lower()

    try:
        chg = changes_store.find("ChangeID", cid)
        if not chg:
            raise ValidationError(f"Промената {cid} не постои.")

        target_status = "implemented" if result == "implemented" else "failed"
        changes_store.update_where("ChangeID", cid, {"Status": target_status})

        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([changes_store])

        msg = (
            f"Промената {cid} е успешно имплементирана!"
            if target_status == "implemented"
            else f"Промената {cid} е означена како неуспешна/вратена назад."
        )
        flash(msg, "info" if target_status == "implemented" else "warning")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("itsm.changes_view"))
