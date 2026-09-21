"""DOCX regression: no unreplaced placeholders in assignment docs."""

import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _doc_text(path):
    return zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")


def _base_data(**over):
    d = {
        "name": "Ана Тест",
        "email": "a@t.mk",
        "company": "Ф",
        "department": "ИТ",
        "manufacturer": "Lenovo",
        "model": "T14",
        "serial": "SN1",
        "asset": "LAP001",
        "date_z": "21.09.2026",
        "date_v": "",
        "da_ne": "",
    }
    d.update(over)
    return d


def test_single_doc_has_no_placeholders(monkeypatch):
    import config
    from services.document_service import fill_zadolzenie

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(config, "DOCUMENTS_DIR", os.path.join(tmp, "documents"))
    rel = fill_zadolzenie(_base_data(), "no_ph_single.docx")
    txt = _doc_text(os.path.join(tmp, rel))
    assert "«" not in txt
    assert "Ана Тест" in txt


def test_multi_doc_has_no_placeholders(monkeypatch):
    import config
    from services.document_service import fill_zadolzenie_multi

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(config, "DOCUMENTS_DIR", os.path.join(tmp, "documents"))
    rel = fill_zadolzenie_multi(
        _base_data(),
        [
            {
                "asset": "LAP001",
                "type": "Laptop",
                "model": "T14",
                "serial": "SN1",
                "manufacturer": "Lenovo",
            }
        ],
        "no_ph_multi.docx",
    )
    txt = _doc_text(os.path.join(tmp, rel))
    assert "«" not in txt
    assert "Ана Тест" in txt
