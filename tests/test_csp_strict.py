"""P2.5: self-hosted fonts and a CSP without inline-style escapes."""

import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _csp(monkeypatch):
    import app as app_mod

    with app_mod.app.test_client() as c:
        return c.get("/login").headers.get("Content-Security-Policy", "")


def test_csp_has_no_inline_or_external_style_origins(monkeypatch):
    csp = _csp(monkeypatch)
    assert "unsafe-inline" not in csp
    assert "fonts.googleapis" not in csp
    assert "fonts.gstatic" not in csp
    assert re.search(r"style-src 'self' 'nonce-[A-Za-z0-9_-]+'", csp), csp
    assert re.search(r"font-src 'self'", csp), csp


def test_templates_have_no_inline_style_attributes():
    offenders = []
    for path in (ROOT / "templates_web").glob("*.html"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\sstyle\s*=", line):
                offenders.append(f"{path.name}:{i}")
    assert offenders == [], offenders


def test_javascript_does_not_emit_inline_style_attributes():
    offenders = []
    for path in (ROOT / "static" / "js").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\sstyle\s*=", text):
            offenders.append(path.name)
    assert offenders == [], offenders


def test_fonts_are_vendored_locally():
    css = (ROOT / "static" / "css" / "fonts.css").read_text(encoding="utf-8")
    assert "https://" not in css
    assert "/static/fonts/" in css
    files = list((ROOT / "static" / "fonts").glob("*.woff2"))
    assert files, "no woff2 files vendored"
    assert any(p.name.startswith("inter-") for p in files)
    assert any(p.name.startswith("sora-") for p in files)


def test_base_does_not_load_google_fonts():
    text = (ROOT / "templates_web" / "base.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in text
    assert "fonts.gstatic" not in text
    assert "/static/css/fonts.css" in text
