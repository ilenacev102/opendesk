"""Brz vnes 8: Ctrl+Enter script wired + autofocus on operation forms."""

import os

TPL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates_web"
)
STATIC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js"
)

FORMS = [
    "assignment.html",
    "replacement.html",
    "repair.html",
    "package.html",
    "reservations.html",
    "requests.html",
    "consumables.html",
    "licenses.html",
    "contracts.html",
    "fields.html",
]


def test_form_keys_script_wired():
    with open(os.path.join(STATIC, "form-keys.js"), encoding="utf-8") as fh:
        js = fh.read()
    assert "requestSubmit" in js
    with open(os.path.join(TPL, "base.html"), encoding="utf-8") as fh:
        assert "form-keys.js" in fh.read()


def test_operation_forms_autofocus():
    for name in FORMS:
        with open(os.path.join(TPL, name), encoding="utf-8") as fh:
            src = fh.read()
        assert "autofocus" in src, name
