"""UI redesign guards: no emoji icons, sprite wired, chrome intact."""

import os
import re

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(BASE, "templates_web")

EMOJI_RE = re.compile(
    "[\U000026a1\U0001f527\U0001f5d1\U0001f4e6\U0001f4e7\U00002705"
    "\U0001f4cb\U000021c4\U0001f5a5\U0001f319\U00002600\U000026a0"
    "\U00002714\U0001f5c4\U0001f4ca\U0001f50d\U0000274c\U00002795"
    "\U0001f4dd\U0001f3e2\U0001f464\U0001f4bb\U0001f5a8\U0001f4f1"
    "\U0001f465\U000023f3\U000026a0\U0000fe0f]"
)


def _templates():
    return [f for f in os.listdir(TPL) if f.endswith(".html") and f != "_icons.html"]


def test_no_emoji_icons_in_templates():
    """Given templates / When scanned / Then no emoji used as icons."""
    offenders = {}
    for name in _templates():
        with open(os.path.join(TPL, name), encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                found = EMOJI_RE.findall(line)
                if found:
                    offenders.setdefault(name, []).append((lineno, "".join(found)))
    assert not offenders, f"Emoji icons remain: {offenders}"


def test_icon_sprite_covers_used_symbols():
    """Given _icons.html / When used symbols collected / Then all defined."""
    with open(os.path.join(TPL, "_icons.html"), encoding="utf-8") as fh:
        sprite = fh.read()
    defined = set(re.findall(r'<symbol id="([^"]+)"', sprite))
    used = set()
    for name in _templates() + ["base.html"]:
        with open(os.path.join(TPL, name), encoding="utf-8") as fh:
            used.update(re.findall(r'href="#([^"]+)"', fh.read()))
    used = {u for u in used if u.startswith("i-")}
    assert used, "No sprite symbols referenced at all"
    assert used <= defined, f"Missing symbols: {used - defined}"


def test_base_shell_chrome():
    """Given base.html / When inspected / Then sprite, skip-link, active nav, svg toggle."""
    with open(os.path.join(TPL, "base.html"), encoding="utf-8") as fh:
        src = fh.read()
    assert "_icons.html" in src
    assert "skip-link" in src
    assert "nav-link" in src and "active" in src
    assert "icon-moon" in src and "icon-sun" in src
    assert "<main" in src


def test_dashboard_redesign_markers():
    """Given dashboard.html / When inspected / Then command center markers remain wired."""
    with open(os.path.join(TPL, "dashboard.html"), encoding="utf-8") as fh:
        src = fh.read()
    assert "workspace-head" in src and "command-strip" in src
    assert "stat-ic" in src and "stat-label" in src
    assert "<thead>" in src
    assert (
        "btn-success" not in src and "btn-warning" not in src and "btn-info" not in src
    )
    assert "sd-theme" in src


def test_routes_render_with_new_chrome():
    """Given app / When key routes hit / Then 200 + sprite refs + no emoji."""
    import app as app_mod

    client = app_mod.app.test_client()
    for url in ["/", "/devices", "/history", "/return", "/device/NOPE"]:
        r = client.get(url)
        assert r.status_code in (200, 404), url
    for url in ["/", "/devices", "/history", "/return", "/replace", "/repair"]:
        html = client.get(url).get_data(as_text=True)
        assert '<use href="#i-' in html, url
        assert EMOJI_RE.search(html) is None, url


def test_sortable_tables_wired():
    """Given list pages / When rendered / Then sortable tables with data-sort headers."""
    import app as app_mod

    client = app_mod.app.test_client()
    for url, marker in [
        ("/devices", "data-sort"),
        ("/history", "data-sort"),
        ("/employees", "table-responsive"),
    ]:
        html = client.get(url).get_data(as_text=True)
        assert "sortable" in html, url
        assert marker in html, url
