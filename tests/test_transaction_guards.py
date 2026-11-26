"""P1.8: static guards against non-atomic writes coming back."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCOPE = ("services", "routes")
STORE_IMPLS = {
    ROOT / "services" / "db_service.py",
    ROOT / "services" / "pg_store.py",
    ROOT / "services" / "store_base.py",
}


def _sources():
    for folder in SCOPE:
        for path in (ROOT / folder).glob("*.py"):
            if path.name == "__pycache__":
                continue
            yield path


def test_no_whole_table_replace_outside_store_implementations():
    offenders = []
    for path in _sources():
        if path in STORE_IMPLS:
            continue
        text = path.read_text(encoding="utf-8")
        if "replace_all(" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"replace_all е забранет во доменски код: {offenders}"


def test_p1_modules_use_the_shared_transaction_helper():
    required = [
        ROOT / "services" / "sprint_service.py",
        ROOT / "services" / "kb_rating.py",
        ROOT / "services" / "auth_service.py",
        ROOT / "services" / "api_token_service.py",
        ROOT / "services" / "popis_service.py",
        ROOT / "services" / "onboard_service.py",
        ROOT / "services" / "project_template.py",
        ROOT / "routes" / "catalog.py",
    ]
    missing = [
        str(p.relative_to(ROOT))
        for p in required
        if "store_transaction" not in p.read_text(encoding="utf-8")
    ]
    assert missing == [], f"мутации без store_transaction: {missing}"


def test_mutation_history_calls_inside_transactions_pass_con():
    """history.log inside a `with ...transaction` block must reuse the con."""
    problems = []
    pattern = re.compile(
        r"with\s+[^\n]*(?:transaction|_tx)\s*\([^\n]*\)\s+as\s+(?P<con>\w+):\n"
        r"(?P<body>(?:[ \t]+.*\n)+)"
    )
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            con = match.group("con")
            body = match.group("body")
            for call in re.finditer(r"history\.log\((.*?)\)\n", body, re.S):
                if f"con={con}" not in call.group(1):
                    line = text[: match.start()].count("\n") + 1
                    problems.append(f"{path.relative_to(ROOT)}:{line}")
    assert problems == [], f"history.log без con во трансакција: {problems}"
