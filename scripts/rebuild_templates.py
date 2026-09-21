"""Rebuild all DOCX templates: neutral, modern, anonymous.

Keeps the exact placeholder contract used by services/document_service.py
(all «KEYS» + the 'Име и презиме на вработен:' paragraph prefix).
No images: a bordered ЛОГО frame users replace with their own logo in Word.
Metadata sanitized (author 'IT ServiceDesk', no personal names).

Usage: python3 scripts/rebuild_templates.py
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

NAVY = RGBColor(0x1F, 0x38, 0x64)
GRAY = RGBColor(0x59, 0x59, 0x59)
LABEL_FILL = "D9E2F3"

POLICY_FOOTER = (
    "Потврдувам дека ги имам прочитано и ќе ги почитувам насоките дадени "
    "во Политиката за одговорно користење на информациски средства."
)


def _shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.makeelement(qn("w:shd"), {})
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def new_doc(title):
    doc = Document()
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)
    core = doc.core_properties
    core.author = "IT ServiceDesk"
    core.last_modified_by = "IT ServiceDesk"
    core.title = title
    core.subject = "IT ServiceDesk"
    core.created = datetime.datetime(2024, 1, 1)
    core.modified = datetime.datetime(2024, 1, 1)
    core.category = ""
    core.comments = ""
    core.identifier = ""
    core.keywords = ""
    core.version = ""
    core.content_status = ""
    core.revision = 1
    return doc


def add_title(doc, title, subtitle="IT ServiceDesk"):
    head = doc.add_table(rows=1, cols=2)
    head.alignment = WD_TABLE_ALIGNMENT.CENTER
    head.columns[0].width = Cm(11.0)
    head.columns[1].width = Cm(5.0)
    left = head.cell(0, 0)
    right = head.cell(0, 1)
    left.vertical_alignment = right.vertical_alignment = 1
    t = left.paragraphs[0].add_run(title)
    t.bold = True
    t.font.size = Pt(17)
    t.font.color.rgb = NAVY
    s = left.add_paragraph().add_run(subtitle)
    s.font.size = Pt(10)
    s.font.color.rgb = GRAY
    frame = right.paragraphs[0]
    frame.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = frame.add_run("ЛОГО")
    r.bold = True
    r.font.size = Pt(14)
    r.font.color.rgb = GRAY
    note = right.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    n = note.add_run("(сопствено лого)")
    n.font.size = Pt(8)
    n.font.color.rgb = GRAY
    _shade(right, "F2F2F2")
    doc.add_paragraph("")


def field_table(doc, rows):
    tbl = doc.add_table(rows=len(rows), cols=2)
    tbl.style = "Table Grid"
    tbl.columns[0].width = Cm(6.0)
    tbl.columns[1].width = Cm(10.0)
    for i, (label, key) in enumerate(rows):
        lab = tbl.cell(i, 0)
        lab.text = ""
        run = lab.paragraphs[0].add_run(label)
        run.bold = True
        run.font.size = Pt(11)
        _shade(lab, LABEL_FILL)
        val = tbl.cell(i, 1)
        val.text = ""
        vrun = val.paragraphs[0].add_run(key)
        vrun.font.size = Pt(11)
    doc.add_paragraph("")


def sig_lines(doc, lines):
    for line in lines:
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.font.size = Pt(11)
    doc.add_paragraph("")


def footer_policy(doc):
    p = doc.add_paragraph()
    run = p.add_run("* " + POLICY_FOOTER)
    run.font.size = Pt(8)
    run.font.color.rgb = GRAY


def save(doc, name):
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
    )
    path = os.path.join(base, name)
    doc.save(path)
    print("rebuilt", path)


def build_zadolzenie():
    doc = new_doc("Задолжување на ИКТ опрема")
    add_title(doc, "Задолжување на ИКТ опрема")
    doc.add_paragraph("Име и презиме на вработен: ")
    field_table(
        doc,
        [
            ("E-mail адреса", "«EMAIL»"),
            ("Компанија", "«КОМПАНИЈА»"),
            ("Оддел", "«ОДДЕЛ»"),
            ("Производител", "«ПРОИЗВОДИТЕЛ»"),
            ("Модел", "«МОДЕЛ»"),
            ("Сериски број", "«СЕРИСКИ_БРОЈ»"),
            ("Инвентарен број", "«ИНВЕНТАРЕН_БРОЈ»"),
            ("Датум на задолжување", "«ДАТУМ_ЗАДОЛЖУВАЊЕ»"),
            ("Датум на враќање", "«ДАТУМ_ВРАЌАЊЕ»"),
            ("Вратен во исправна состојба", "«ДА_НЕ»"),
        ],
    )
    sig_lines(
        doc,
        [
            "Примил (Вработен: «ИМЕ_ПРЕЗИМЕ»): ____________________   Датум: __________",
            "Вратил: ____________________   Датум: __________   потпис: __________",
        ],
    )
    footer_policy(doc)
    save(doc, "Zadolzuvanje_Template.docx")


def build_zamena():
    doc = new_doc("Замена на ИКТ опрема")
    add_title(doc, "Замена на ИКТ опрема")
    doc.add_paragraph("Име и презиме на вработен: «ИМЕ_ПРЕЗИМЕ»")
    field_table(
        doc,
        [
            ("E-mail адреса", "«EMAIL»"),
            ("Компанија", "«КОМПАНИЈА»"),
            ("Оддел", "«ОДДЕЛ»"),
            ("Причина за замена", "«ПРИЧИНА»"),
            ("Датум", "«ДАТУМ»"),
        ],
    )
    p = doc.add_paragraph()
    r = p.add_run("СТАР УРЕД")
    r.bold = True
    r.font.color.rgb = NAVY
    field_table(
        doc,
        [
            ("Производител", "«СТАР_ПРОИЗВОДИТЕЛ»"),
            ("Модел", "«СТАР_МОДЕЛ»"),
            ("Сериски број", "«СТАР_СЕРИСКИ_БРОЈ»"),
            ("Инвентарен број", "«СТАР_ИНВЕНТАРЕН_БРОЈ»"),
        ],
    )
    p = doc.add_paragraph()
    r = p.add_run("НОВ УРЕД")
    r.bold = True
    r.font.color.rgb = NAVY
    field_table(
        doc,
        [
            ("Производител", "«НОВ_ПРОИЗВОДИТЕЛ»"),
            ("Модел", "«НОВ_МОДЕЛ»"),
            ("Сериски број", "«НОВ_СЕРИСКИ_БРОЈ»"),
            ("Инвентарен број", "«НОВ_ИНВЕНТАРЕН_БРОЈ»"),
        ],
    )
    sig_lines(
        doc,
        [
            "Предал, потпис: ____________________",
            "Примил, потпис: ____________________",
        ],
    )
    footer_policy(doc)
    save(doc, "Zamena_Template.docx")


def build_servis():
    doc = new_doc("Упат за сервис на ИКТ опрема")
    add_title(doc, "Упат за сервис на ИКТ опрема")
    doc.add_paragraph("Име и презиме на вработен: «ИМЕ_ПРЕЗИМЕ»")
    field_table(
        doc,
        [
            ("E-mail адреса", "«EMAIL»"),
            ("Компанија", "«КОМПАНИЈА»"),
            ("Оддел", "«ОДДЕЛ»"),
            ("Производител", "«ПРОИЗВОДИТЕЛ»"),
            ("Модел", "«МОДЕЛ»"),
            ("Сериски број", "«СЕРИСКИ_БРОЈ»"),
            ("Инвентарен број", "«ИНВЕНТАРЕН_БРОЈ»"),
            ("Опис на дефект", "«ДЕФЕКТ»"),
            ("Сервисер", "«СЕРВИСЕР»"),
            ("Испратен на датум", "«ДАТУМ_ИСПРАЌАЊЕ»"),
            ("Вратен од сервис, датум", "«ДАТУМ_ВРАЌАЊЕ»"),
            ("Вратен во исправна состојба", "«ДА_НЕ»"),
        ],
    )
    sig_lines(doc, ["потпис: ____________________"])
    footer_policy(doc)
    save(doc, "Servis_Template.docx")


def build_rashod():
    doc = new_doc("Записник за расходување на ИКТ опрема")
    add_title(doc, "Записник за расходување на ИКТ опрема")
    field_table(
        doc,
        [
            ("Производител", "«ПРОИЗВОДИТЕЛ»"),
            ("Модел", "«МОДЕЛ»"),
            ("Сериски број", "«СЕРИСКИ_БРОЈ»"),
            ("Инвентарен број", "«ИНВЕНТАРЕН_БРОЈ»"),
            ("Тип на уред", "«ТИП»"),
            ("Причина за расход", "«ПРИЧИНА»"),
            ("Начин на расходување", "«НАЧИН»"),
            ("Комисија", "«КОМИСИЈА»"),
            ("Датум", "«ДАТУМ»"),
        ],
    )
    sig_lines(
        doc,
        [
            "Потпис на комисија:",
            "1. ____________________",
            "2. ____________________",
            "3. ____________________",
        ],
    )
    footer_policy(doc)
    save(doc, "Rashod_Template.docx")


def build_popis():
    doc = new_doc("Записник од попис на ИКТ опрема")
    add_title(doc, "Записник од попис на ИКТ опрема")
    field_table(
        doc,
        [
            ("Опфат", "«ОПФАТ»"),
            ("Датум", "«ДАТУМ»"),
            ("Очекувани уреди", "«ОЧЕКУВАНИ»"),
            ("Најдени", "«НАЈДЕНИ»"),
            ("Недостасуваат", "«НЕДОСТАСУВААТ»"),
        ],
    )
    sig_lines(doc, ["Комисија: ____________________   Потпис: ____________________"])
    footer_policy(doc)
    save(doc, "Popis_Template.docx")


if __name__ == "__main__":
    build_zadolzenie()
    build_zamena()
    build_servis()
    build_rashod()
    build_popis()
