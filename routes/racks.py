"""Visual 42U Server Rack Elevation Designer (Flask Blueprint): /racks.

Provides visual data center & server room rack elevation management (Snipe-IT / Device42 style):
- 42U standard rack elevation grid with U1..U42 units.
- Mounting and unmounting servers, switches, patch panels, UPS units.
- Collision and height validation (1U, 2U, 4U, etc.).
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from utils.validators import ValidationError

bp = Blueprint("racks", __name__)


def _parse_u(val, label):
    try:
        n = int(str(val).strip())
        if n < 1:
            raise ValueError()
        return n
    except (ValueError, TypeError):
        raise ValidationError(f"Невалидна вредност за {label}: мора да биде позитивен број.")


@bp.route("/racks", methods=["GET", "POST"])
def racks_view():
    import app as app_mod
    import config
    from utils.helpers import next_id

    racks = app_mod.racks
    rack_items = app_mod.rack_items
    devices = getattr(app_mod, "devices", None)

    if request.method == "POST":
        # Create new rack
        name = request.form.get("name", "").strip()
        loc = request.form.get("location", "").strip()
        units_raw = request.form.get("units", "42").strip()
        notes = request.form.get("notes", "").strip()
        try:
            if not name:
                raise ValidationError("Името на ормарот е задолжително.")
            units = _parse_u(units_raw, "број на единици (U)")
            rid = request.form.get("rack_id", "").strip() or next_id(racks, "RackID", "RCK")
            if racks.find("RackID", rid):
                raise ValidationError(f"Ормарот {rid} веќе постои.")
            racks.append_row({
                "RackID": rid,
                "Name": name,
                "Location": loc,
                "Units": str(units),
                "Notes": notes,
            })
            if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
                app_mod.backup_all([racks])
            flash(f"Серверскиот ормар {rid} ({name}) е успешно додаден.", "success")
            return redirect(url_for("racks.racks_view", rack_id=rid))
        except ValidationError as exc:
            flash(f"ГРЕШКА: {exc}", "danger")
            return redirect(url_for("racks.racks_view"))

    all_racks = racks.records()
    # Default seed if empty
    if not all_racks:
        default_rack = {
            "RackID": "RCK-01",
            "Name": "Главен Серверски Ормар 1",
            "Location": "Сервер сала (Кат -1)",
            "Units": "42",
            "Notes": "Стандарден 42U ормар за продукциски сервери",
        }
        racks.append_row(default_rack)
        all_racks = [default_rack]

    selected_id = request.args.get("rack_id", "").strip()
    selected_rack = None
    if selected_id:
        selected_rack = racks.find("RackID", selected_id)
    if not selected_rack and all_racks:
        selected_rack = all_racks[0]
        selected_id = selected_rack["RackID"]

    total_units = int(selected_rack.get("Units") or 42) if selected_rack else 42
    items = rack_items.filter_eq("RackID", selected_id) if selected_rack else []

    # Map items by unit coverage
    unit_map = {}
    occupied_count = 0
    for item in items:
        start = int(item.get("StartUnit") or 1)
        height = int(item.get("HeightUnits") or 1)
        top = start + height - 1
        asset_id = item.get("AssetID", "")
        dev = devices.find("AssetID", asset_id) if devices else None
        item_info = {
            "item_id": item.get("ItemID", ""),
            "asset_id": asset_id,
            "start_unit": start,
            "height_units": height,
            "notes": item.get("Notes", ""),
            "device": dev,
        }
        for u in range(start, top + 1):
            if u == top:
                unit_map[u] = {"type": "top", "item": item_info}
            else:
                unit_map[u] = {"type": "body", "item": item_info}
            occupied_count += 1

    # Build ordered unit slots: 42 down to 1
    slots = []
    for u in range(total_units, 0, -1):
        slot_data = unit_map.get(u)
        if slot_data:
            slots.append({"u": u, "state": slot_data["type"], "item": slot_data["item"]})
        else:
            slots.append({"u": u, "state": "empty", "item": None})

    free_count = max(0, total_units - occupied_count)
    usage_pct = round((occupied_count / total_units) * 100) if total_units > 0 else 0

    all_devices = devices.records() if devices else []

    return render_template(
        "racks.html",
        all_racks=all_racks,
        selected_rack=selected_rack,
        slots=slots,
        total_units=total_units,
        occupied_count=occupied_count,
        free_count=free_count,
        usage_pct=usage_pct,
        all_devices=all_devices,
    )


@bp.route("/racks/assign", methods=["POST"])
def racks_assign():
    import app as app_mod
    import config
    from utils.helpers import next_id

    racks = app_mod.racks
    rack_items = app_mod.rack_items

    rid = request.form.get("rack_id", "").strip()
    asset_id = request.form.get("asset_id", "").strip()
    notes = request.form.get("notes", "").strip()

    try:
        rack = racks.find("RackID", rid)
        if not rack:
            raise ValidationError(f"Ормарот {rid} не постои.")
        if not asset_id:
            raise ValidationError("Изберете уред за монтирање во ормарот.")

        start_u = _parse_u(request.form.get("start_unit"), "почетна единица (U)")
        height_u = _parse_u(request.form.get("height_units", "1"), "висина (U)")
        total_u = int(rack.get("Units") or 42)

        if start_u > total_u:
            raise ValidationError(f"Почетната позиција U{start_u} го надминува капацитетот на ормарот (U{total_u}).")
        end_u = start_u + height_u - 1
        if end_u > total_u:
            raise ValidationError(f"Уредот со висина {height_u}U надминува од горниот лимит на ормарот (U{total_u}).")

        # Collision detection
        existing_items = rack_items.filter_eq("RackID", rid)
        for it in existing_items:
            e_start = int(it.get("StartUnit") or 1)
            e_end = e_start + int(it.get("HeightUnits") or 1) - 1
            # Check overlap
            if max(start_u, e_start) <= min(end_u, e_end):
                raise ValidationError(
                    f"Конфликт: Слотовите U{start_u}-U{end_u} се поклопуваат со веќе монтиран уред {it.get('AssetID')} (U{e_start}-U{e_end})."
                )

        item_id = next_id(rack_items, "ItemID", "RIT")
        rack_items.append_row({
            "ItemID": item_id,
            "RackID": rid,
            "AssetID": asset_id,
            "StartUnit": str(start_u),
            "HeightUnits": str(height_u),
            "Notes": notes,
        })
        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([rack_items])

        flash(f"Уредот {asset_id} е монтиран на U{start_u} ({height_u}U) во {rid}.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("racks.racks_view", rack_id=rid))


@bp.route("/racks/remove", methods=["POST"])
def racks_remove():
    import app as app_mod
    import config

    rack_items = app_mod.rack_items
    item_id = request.form.get("item_id", "").strip()
    rid = request.form.get("rack_id", "").strip()

    try:
        item = rack_items.find("ItemID", item_id)
        if not item:
            raise ValidationError(f"Записот {item_id} не постои.")
        rid = item.get("RackID", rid)
        rack_items.delete_where("ItemID", item_id)
        if config.BACKUP_ON_WRITE and hasattr(app_mod, "backup_all"):
            app_mod.backup_all([rack_items])
        flash(f"Уредот {item.get('AssetID')} е демонтиран од ормарот.", "success")
    except ValidationError as exc:
        flash(f"ГРЕШКА: {exc}", "danger")

    return redirect(url_for("racks.racks_view", rack_id=rid))
