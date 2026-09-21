"""Public-version guard: templates must carry no vendor branding or personal data."""

import base64
import glob
import hashlib
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(BASE, "templates")


def _forbidden_markers():
    encoded = [
        "RVZO",
        "0JXQktCd",
        "QXZyb3NpZXZza2E=",
        "TmFjZXY=",
        "R2lua2E=",
    ]
    return [base64.b64decode(e).decode("utf-8") for e in encoded]


FORBIDDEN_TEXT = _forbidden_markers()
FORBIDDEN_LOGO_SHA256 = {
    # original vendor logo removed from the public templates
    "23f84e42e6714ffe52b62bed04929fa259c2738bd58403db42b10747e3cc99c1",
}


def _package_text(path):
    z = zipfile.ZipFile(path)
    out = []
    for n in z.namelist():
        if n.endswith((".xml", ".rels")):
            out.append(z.read(n).decode("utf-8", "replace"))
    return "\n".join(out)


def test_no_branding_text_in_templates():
    bad = []
    for path in sorted(glob.glob(os.path.join(TPL, "*.docx"))):
        text = _package_text(path)
        for marker in FORBIDDEN_TEXT:
            if marker in text:
                bad.append(f"{os.path.basename(path)}: {marker!r}")
    assert bad == [], bad


def test_no_vendor_logo_bytes():
    bad = []
    for path in sorted(glob.glob(os.path.join(TPL, "*.docx"))):
        z = zipfile.ZipFile(path)
        for n in z.namelist():
            if "/media/" in n and not n.endswith("/"):
                digest = hashlib.sha256(z.read(n)).hexdigest()
                if digest in FORBIDDEN_LOGO_SHA256:
                    bad.append(f"{os.path.basename(path)}:{n}")
    assert bad == [], bad


def test_templates_dir_env_override(monkeypatch):
    import importlib

    import config

    monkeypatch.setenv("SERVICEDESK_TEMPLATES_DIR", "/tmp/custom-tpl")
    importlib.reload(config)
    try:
        assert config.TEMPLATES_DIR == "/tmp/custom-tpl"
    finally:
        monkeypatch.delenv("SERVICEDESK_TEMPLATES_DIR")
        importlib.reload(config)
