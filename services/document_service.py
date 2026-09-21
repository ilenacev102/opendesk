"""Word documents: fill corporate template when available, else build."""

import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

import config

TEMPLATE = os.path.join(config.TEMPLATES_DIR, "Zadolzuvanje_Template.docx")


def _replace(container, mapping):
    for para in container.paragraphs:
        for key, val in mapping.items():
            if key in para.text:
                for run in para.runs:
                    if key in run.text:
                        run.text = run.text.replace(key, val)
                if key in para.text:
                    para.text = para.text.replace(key, val)
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                _replace(cell, mapping)


def _embed_signature(doc, data):
    """Append captured signature image when a valid file path is given."""
    sig = str((data or {}).get("signature_path", "") or "")
    if not sig:
        return
    if not os.path.isabs(sig):
        sig = os.path.join(os.path.dirname(config.DOCUMENTS_DIR), sig)
    if not os.path.isfile(sig):
        return
    doc.add_paragraph("")
    cap = doc.add_paragraph()
    run = cap.add_run("Потпис на вработен:")
    run.bold = True
    try:
        doc.add_picture(sig, width=Cm(5))
    except Exception:
        pass


def fill_template(template_name, mapping, filename, subdir):
    """Fill any corporate template with «PLACEHOLDER» mapping."""
    doc = Document(os.path.join(config.TEMPLATES_DIR, template_name))
    _replace(doc, mapping)
    folder = os.path.join(config.DOCUMENTS_DIR, subdir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    doc.save(path)
    return os.path.join("documents", subdir, filename)


def mk_date():
    parts = stamp_today().split("-")
    return f"{parts[2]}.{parts[1]}.{parts[0]}"


def stamp_today():
    import datetime

    return datetime.date.today().isoformat()


def fill_zadolzenie_multi(data, items, filename, subdir="assignments"):
    """Same template + appended table when multiple devices share one doc."""
    doc = Document(TEMPLATE)
    for para in doc.paragraphs:
        if para.text.strip().startswith("Име и презиме на вработен:"):
            para.text = f"Име и презиме на вработен: {data['name']}"
    single = dict(data)
    single.update(
        {
            "manufacturer": "—",
            "model": "види список",
            "serial": "—",
            "asset": f"{len(items)} уреди",
        }
    )
    _replace(
        doc,
        {
            "«ИМЕ_ПРЕЗИМЕ»": single.get("name", ""),
            "«EMAIL»": single.get("email", ""),
            "«КОМПАНИЈА»": single.get("company", ""),
            "«ОДДЕЛ»": single.get("department", ""),
            "«ПРОИЗВОДИТЕЛ»": single.get("manufacturer", ""),
            "«МОДЕЛ»": single.get("model", ""),
            "«СЕРИСКИ_БРОЈ»": single.get("serial", ""),
            "«ИНВЕНТАРЕН_БРОЈ»": single.get("asset", ""),
            "«ДАТУМ_ЗАДОЛЖУВАЊЕ»": single.get("date_z", ""),
            "«ДАТУМ_ВРАЌАЊЕ»": single.get("date_v", ""),
            "«ДА_НЕ»": single.get("da_ne", ""),
        },
    )
    doc.add_paragraph("")
    head = doc.add_paragraph()
    run = head.add_run("Список на уреди:")
    run.bold = True
    tbl = doc.add_table(rows=1 + len(items), cols=4)
    try:
        tbl.style = "Table Grid"
    except KeyError:
        pass
    for j, header in enumerate(
        ["Инв.број", "Тип/Модел", "Сериски број", "Производител"]
    ):
        cell = tbl.cell(0, j)
        cell.text = ""
        bold = cell.paragraphs[0].add_run(header)
        bold.bold = True
    for i, dev in enumerate(items, 1):
        tbl.cell(i, 0).text = dev.get("asset", "")
        tbl.cell(i, 1).text = f"{dev.get('type', '')} {dev.get('model', '')}"
        tbl.cell(i, 2).text = dev.get("serial", "")
        tbl.cell(i, 3).text = dev.get("manufacturer", "")
    _embed_signature(doc, single)
    folder = os.path.join(config.DOCUMENTS_DIR, subdir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    doc.save(path)
    return os.path.join("documents", subdir, filename)


def fill_zadolzenie(data, filename, subdir="assignments"):
    """Populate Zadolzuvanje_Template.docx with live data."""
    doc = Document(TEMPLATE)
    for para in doc.paragraphs:
        if para.text.strip().startswith("Име и презиме на вработен:"):
            para.text = f"Име и презиме на вработен: {data['name']}"
    _replace(
        doc,
        {
            "«ИМЕ_ПРЕЗИМЕ»": data.get("name", ""),
            "«EMAIL»": data.get("email", ""),
            "«КОМПАНИЈА»": data.get("company", ""),
            "«ОДДЕЛ»": data.get("department", ""),
            "«ПРОИЗВОДИТЕЛ»": data.get("manufacturer", ""),
            "«МОДЕЛ»": data.get("model", ""),
            "«СЕРИСКИ_БРОЈ»": data.get("serial", ""),
            "«ИНВЕНТАРЕН_БРОЈ»": data.get("asset", ""),
            "«ДАТУМ_ЗАДОЛЖУВАЊЕ»": data.get("date_z", ""),
            "«ДАТУМ_ВРАЌАЊЕ»": data.get("date_v", ""),
            "«ДА_НЕ»": data.get("da_ne", ""),
        },
    )
    _embed_signature(doc, data)
    folder = os.path.join(config.DOCUMENTS_DIR, subdir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    doc.save(path)
    return os.path.join("documents", subdir, filename)


def _base(title, doc_no, rows):
    doc = Document()
    head = doc.add_paragraph()
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = head.add_run(title)
    run.bold = True
    run.font.size = Pt(16)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(f"Бр. {doc_no}")
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    for i, (label, value) in enumerate(rows):
        cell = table.cell(i, 0)
        cell.text = ""
        bold = cell.paragraphs[0].add_run(label)
        bold.bold = True
        table.cell(i, 1).text = value
    doc.add_paragraph("")
    sig = doc.add_paragraph()
    sig.add_run(
        "Вработен: ____________________\t\tIT ServiceDesk: ____________________"
    )
    doc.add_paragraph("(потпис)\t\t\t(потпис)")
    return doc


def save_doc(kind, filename, title, rows):
    folder = os.path.join(config.DOCUMENTS_DIR, kind)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    _base(title, filename.replace(".docx", ""), rows).save(path)
    return os.path.join("documents", kind, filename)
