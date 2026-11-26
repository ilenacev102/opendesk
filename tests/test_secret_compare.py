"""P2.4: every secret comparison stays constant-time (guard against regressions)."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _text(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_csrf_and_api_tokens_use_compare_digest():
    assert "hmac.compare_digest" in _text("services", "csrf.py")
    assert "hmac.compare_digest" in _text("services", "api_token_service.py")


def test_no_direct_equality_on_secret_fields():
    pattern = re.compile(
        r"(?:TokenHash|Signature|Secret|_csrf_token|password_hash)\s*(?:==|!=)"
    )
    offenders = []
    for folder in ("services", "routes", "utils"):
        for path in (ROOT / folder).glob("*.py"):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert offenders == [], offenders


def test_password_verification_uses_werkzeug_hash():
    text = _text("services", "auth_service.py")
    assert "check_password_hash" in text
    assert "generate_password_hash" in text
