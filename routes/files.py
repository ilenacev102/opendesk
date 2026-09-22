"""Files routes (Flask Blueprint): qr, labels, doc/pdf downloads.

App-owned names are imported lazily INSIDE each view so they always resolve
against the live ``app`` module (test monkeypatching keeps working).
"""

import os

from flask import Blueprint, abort, render_template, request, send_file

bp = Blueprint("files", __name__)

log = __import__("logging").getLogger("servicedesk")


@bp.route("/qr/<asset_id>")
def qr_image(asset_id):
    from app import devices
    from services.qr_service import qr_png_bytes

    dev = devices.find("AssetID", asset_id)
    if dev is None:
        abort(404)
    try:
        png = qr_png_bytes(asset_id, request.host_url)
    except ValueError:
        abort(404)
    import io as _io

    return send_file(
        _io.BytesIO(png),
        mimetype="image/png",
        download_name=f"{asset_id}.png",
    )


@bp.route("/labels")
def labels():
    from app import devices

    st = (request.args.get("status") or "").strip()
    tp = (request.args.get("type") or "").strip()
    loc = (request.args.get("loc") or "").strip()
    rows = []
    for d in devices.records():
        if st and d.get("Status") != st:
            continue
        if tp and d.get("Type") != tp:
            continue
        if loc and d.get("Location") != loc:
            continue
        rows.append(d)
    return render_template("labels.html", rows=rows, st=st, tp=tp, loc=loc)


@bp.route("/doc/<path:rel>")
def download_doc(rel):
    import config

    docs_base = os.path.abspath(config.DOCUMENTS_DIR)
    root_base = os.path.abspath(config.BASE_DIR)
    clean = (rel or "").lstrip("/\\")
    full = os.path.abspath(os.path.join(root_base, clean))
    if os.path.commonpath([docs_base, full]) != docs_base:
        abort(404)
    if not os.path.isfile(full):
        abort(404)
    return send_file(full)


@bp.route("/pdf/<path:rel>")
def download_pdf(rel):
    import subprocess

    import config

    docs_base = os.path.abspath(config.DOCUMENTS_DIR)
    root_base = os.path.abspath(config.BASE_DIR)
    clean = (rel or "").lstrip("/\\")
    # only .docx inside documents/ can be converted
    if not clean.lower().endswith(".docx"):
        abort(404)
    full = os.path.abspath(os.path.join(root_base, clean))
    if os.path.commonpath([docs_base, full]) != docs_base:
        abort(404)
    if not os.path.isfile(full):
        abort(404)
    pdf = os.path.splitext(full)[0] + ".pdf"
    if not os.path.exists(pdf) or (os.path.getmtime(full) > os.path.getmtime(pdf)):
        outdir = os.path.dirname(full)
        proc = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", outdir, full],
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0 or not os.path.exists(pdf):
            log.error("PDF convert failed: %s", proc.stderr.decode()[-500:])
            abort(500)
    return send_file(pdf)
