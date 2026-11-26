"""Tests for scripts/log_report.py (Task 4 of the observability plan)."""

import importlib.util
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "log_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("log_report", SPEC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _line(status, route="r", ms=10.0, rid="x", msg="request"):
    import json

    return json.dumps(
        {
            "msg": msg,
            "method": "GET",
            "route": route,
            "status": status,
            "duration_ms": ms,
            "request_id": rid,
        }
    )


def test_summarize_counts_only_request_lines():
    mod = _load()
    out = mod.summarize(
        [
            _line(200),
            _line(200),
            _line(500),
            _line(429, rid="y"),
            _line(200, msg="notify failed"),
            "{not json",
            "",
        ]
    )
    assert out["requests"] == 4
    assert out["classes"] == {"2xx": 2, "3xx": 0, "4xx": 1, "5xx": 1}
    assert out["rate_limited"] == 1
    assert out["service_lines"] == 1
    assert out["skipped"] == 1
    assert out["ids"] == 2


def test_summarize_since_filters_and_bad_since_raises_value_error():
    import pytest

    mod = _load()
    assert mod.summarize([_line(200)])["requests"] == 1
    with pytest.raises(ValueError):
        mod.summarize([_line(200)], since="not-a-date")


def test_summarize_computes_exact_route_p95():
    mod = _load()
    lines = [_line(200, ms=float(ms)) for ms in (10, 20, 30, 40, 5000)]
    out = mod.summarize(lines)
    assert out["routes"][0]["p95_ms"] == 5000
    assert out["routes"][0]["count"] == 5


def test_main_reads_file_and_reports(tmp_path, capsys):
    mod = _load()
    log = tmp_path / "a.log"
    log.write_text(_line(200) + "\n" + _line(503) + "\n", encoding="utf-8")
    assert mod.main(["--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "Requests: 2" in out and "5xx" in out


def test_main_reads_stdin(monkeypatch, capsys):
    import io

    mod = _load()
    monkeypatch.setattr("sys.stdin", io.StringIO(_line(200) + "\n"))
    assert mod.main(["--log", "-"]) == 0
    assert "Requests: 1" in capsys.readouterr().out


def test_main_missing_file_returns_2(tmp_path, capsys):
    mod = _load()
    assert mod.main(["--log", str(tmp_path / "nope.log")]) == 2
    assert "cannot read" in capsys.readouterr().err
