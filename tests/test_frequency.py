"""Brz vnes 5: frequency ranking in autocomplete (node harness, skips w/o node)."""

import os
import shutil
import subprocess

import pytest

HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "freq_harness.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_frequency_promotes_picked_item():
    r = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "OK top=E2" in r.stdout
