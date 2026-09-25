"""Discovery Pro todo 2: agent collector scripts (tests-after)."""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PS1 = os.path.join(REPO, "agents", "heartbeat.ps1")
SH = os.path.join(REPO, "agents", "heartbeat.sh")
README = os.path.join(REPO, "agents", "README.md")

REQUIRED_FIELDS = ["hostname", "serial", "manufacturer", "model", "os"]


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_scripts_exist():
    assert os.path.isfile(PS1), "agents/heartbeat.ps1 missing"
    assert os.path.isfile(SH), "agents/heartbeat.sh missing"
    assert os.path.isfile(README), "agents/README.md missing"


def test_scripts_post_all_fields():
    for path in (PS1, SH):
        text = _text(path).lower()
        for field in REQUIRED_FIELDS:
            assert field in text, f"{path} missing field {field}"


def test_scripts_use_env_only():
    for path in (PS1, SH):
        text = _text(path)
        assert "SERVICEDESK_URL" in text
        assert "SERVICEDESK_TOKEN" in text
        code_lines = [
            line
            for line in text.splitlines()
            if not line.strip().startswith("#") and not line.strip().startswith("<#")
        ]
        code = "\n".join(code_lines)
        for line in code_lines:
            assert not re.search(r"https?://[a-zA-Z0-9]", line), (
                f"hardcoded URL in {path}: {line.strip()[:60]}"
            )
        assert "Bearer " not in code or "$" in code.split("Bearer ")[1][:8], (
            f"hardcoded token in {path}"
        )


def test_sh_syntax_valid():
    result = subprocess.run(
        ["bash", "-n", SH], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_sh_dry_run_parses_sample():
    env = dict(os.environ)
    env["SERVICEDESK_URL"] = "http://127.0.0.1:9"
    env["SERVICEDESK_TOKEN"] = "dry-run"
    env["SERVICEDESK_DRY_RUN"] = "1"
    env["HOSTNAME_OVERRIDE"] = "TEST-PC"
    env["SERIAL_OVERRIDE"] = "TEST123"
    result = subprocess.run(
        ["bash", SH], capture_output=True, text=True, timeout=30, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "TEST-PC" in result.stdout
    assert "TEST123" in result.stdout


def test_readme_has_install():
    text = _text(README)
    assert "Task Scheduler" in text or "cron" in text
    assert "SERVICEDESK_TOKEN" in text
