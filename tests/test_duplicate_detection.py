"""Sprint 6: duplicate detection at triage — Jaccard similarity, API, triage panel."""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schemas import INCIDENT_COLS


def _store(db, table, cols):
    from services.db_service import DbStore

    return DbStore(db, table, cols)


def _db():
    return os.path.join(tempfile.mkdtemp(), "dupes.db")


def _add(
    incidents, iid, title, status="open", linked="", created="2026-11-10 09:00:00"
):
    incidents.append_row(
        {
            "IncidentID": iid,
            "Title": title,
            "Status": status,
            "ProjectID": "PRJ-1",
            "LinkedTo": linked,
            "Created": created,
        }
    )


def test_similarity_identical_titles_is_one():
    from services.duplicate_service import similarity

    assert similarity("Паднат интернет на кат 2", "Паднат интернет на кат 2") == 1.0


def test_similarity_disjoint_titles_is_zero():
    from services.duplicate_service import similarity

    assert similarity("Принтер без тонер", "Лаптоп не се полни") == 0.0


def test_similarity_partial_overlap_between_zero_and_one():
    from services.duplicate_service import similarity

    score = similarity("Паднат интернет на кат 2", "Нема интернет на кат 3")
    assert 0.0 < score < 1.0


def test_similarity_empty_title_is_zero():
    from services.duplicate_service import similarity

    assert similarity("", "Нешто") == 0.0


def test_detect_returns_active_matches_sorted_by_score():
    from services import duplicate_service

    incidents = _store(_db(), "incidents", INCIDENT_COLS)
    _add(incidents, "I-1", "Паднат интернет на кат 2")
    _add(incidents, "I-2", "Нема интернет на кат 2", status="in-progress")
    _add(incidents, "I-3", "Паднат интернет на кат 5")
    _add(incidents, "I-4", "Принтер без тонер")
    _add(incidents, "I-5", "Паднат интернет на кат 2", status="resolved")

    rows = duplicate_service.detect(incidents, "Паднат интернет на кат 2")
    ids = [r["IncidentID"] for r in rows]
    assert "I-1" in ids and "I-2" in ids
    assert "I-4" not in ids  # no overlap
    assert "I-5" not in ids  # resolved → not active
    # exact duplicate first
    assert rows[0]["IncidentID"] == "I-1"
    assert all(r["Score"] > 0 for r in rows)


def test_detect_skips_linked_and_self():
    from services import duplicate_service

    incidents = _store(_db(), "incidents", INCIDENT_COLS)
    _add(incidents, "I-1", "Паднат интернет на кат 2", linked="I-9")
    _add(incidents, "I-2", "Паднат интернет на кат 2")
    rows = duplicate_service.detect(
        incidents, "Паднат интернет на кат 2", exclude_id="I-2"
    )
    # Already-linked incidents are not suggested (no duplicate re-linking);
    # self is excluded via exclude_id.
    assert rows == []


def test_detect_respects_threshold_and_limit():
    from services import duplicate_service

    incidents = _store(_db(), "incidents", INCIDENT_COLS)
    _add(incidents, "I-1", "Паднат интернет на кат 2")
    _add(incidents, "I-2", "Нема интернет на кат 3")
    _add(incidents, "I-3", "Принтер без тонер")

    strict = duplicate_service.detect(
        incidents, "Паднат интернет на кат 2", threshold=0.9
    )
    assert [r["IncidentID"] for r in strict] == ["I-1"]

    loose = duplicate_service.detect(incidents, "Паднат интернет на кат 2", limit=2)
    assert len(loose) <= 2


def test_detect_empty_title_returns_empty():
    from services import duplicate_service

    incidents = _store(_db(), "incidents", INCIDENT_COLS)
    _add(incidents, "I-1", "Паднат интернет")
    assert duplicate_service.detect(incidents, "   ") == []


@pytest.fixture()
def dup_env(monkeypatch):
    import app as app_mod
    from services import ratelimit as rl
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import ISSUE_TYPE_COLS, PROJECT_COLS

    rl.reset()
    db = _db()
    incidents = _store(db, "incidents", INCIDENT_COLS)
    _add(incidents, "I-1", "Паднат интернет на кат 2")
    _add(incidents, "I-2", "Нема интернет на кат 2", status="in-progress")
    _add(incidents, "I-3", "Паднат интернет на кат 2", status="resolved")
    monkeypatch.setattr(app_mod, "incidents", incidents)
    monkeypatch.setattr(app_mod, "projects", _store(db, "projects", PROJECT_COLS))
    monkeypatch.setattr(
        app_mod, "project_types", _store(db, "issue_types", ISSUE_TYPE_COLS)
    )
    monkeypatch.setattr(
        app_mod, "history", HistoryService(_store(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)

    def _wipe():
        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()

    _wipe()
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")

    def _client():
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        return c

    try:
        yield {"app": app_mod, "client": _client, "incidents": incidents}
    finally:
        _wipe()


def test_api_detect_duplicates_returns_matches(dup_env):
    r = dup_env["client"]().get(
        "/api/v1/incidents/detect-duplicates",
        query_string={"title": "Паднат интернет на кат 2"},
    )
    assert r.status_code == 200
    data = r.get_json()
    ids = [m["IncidentID"] for m in data["matches"]]
    assert "I-1" in ids and "I-2" in ids
    assert "I-3" not in ids
    match = data["matches"][0]
    assert set(match) >= {"IncidentID", "Title", "Status", "Score"}


def test_api_detect_duplicates_requires_login(dup_env):
    c = dup_env["app"].app.test_client()
    r = c.get("/api/v1/incidents/detect-duplicates", query_string={"title": "x"})
    assert r.status_code in (302, 401)


def test_api_detect_duplicates_empty_title_empty_matches(dup_env):
    r = dup_env["client"]().get(
        "/api/v1/incidents/detect-duplicates", query_string={"title": ""}
    )
    assert r.status_code == 200
    assert r.get_json()["matches"] == []


def test_incident_detail_shows_similar_panel(dup_env):
    """Active unlinked incident page lists similar active incidents with 1-click link."""
    c = dup_env["client"]()
    r = c.get("/incident/I-1")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Слични активни инциденти" in body
    assert "I-2" in body


def test_incident_detail_resolved_hides_panel(dup_env):
    c = dup_env["client"]()
    r = c.get("/incident/I-3")
    body = r.get_data(as_text=True)
    assert "Слични активни инциденти" not in body


def test_new_incident_form_has_duplicate_detector(dup_env):
    c = dup_env["client"]()
    r = c.get("/incidents")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "dupDetector" in body
    assert "detect-duplicates" in body
