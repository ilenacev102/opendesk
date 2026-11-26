"""F5: KB ratings — vote upsert, average, ranked order, rate route."""

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _store():
    from services.db_service import DbStore
    from services.schemas import KB_RATING_COLS

    tmp = tempfile.mkdtemp()
    return DbStore(os.path.join(tmp, "kbr.db"), "kb_ratings", KB_RATING_COLS)


def test_vote_upserts_single_row():
    from services.kb_rating import vote

    store = _store()
    vote(store, "KB000001", "u1", 4)
    vote(store, "KB000001", "u1", 5)
    rows = [r for r in store.records() if r["ArticleID"] == "KB000001"]
    assert len(rows) == 1
    assert int(rows[0]["Score"]) == 5
    vote(store, "KB000001", "u2", 3)
    assert len(store.records()) == 2


def test_average_and_unrated():
    from services.kb_rating import average, vote

    store = _store()
    assert average(store, "KB000001") is None
    vote(store, "KB000001", "u1", 4)
    vote(store, "KB000001", "u2", 5)
    assert average(store, "KB000001") == 4.5


def test_ranked_orders_rated_first():
    from services.kb_rating import ranked, vote

    store = _store()
    arts = [{"ArticleID": "A"}, {"ArticleID": "B"}, {"ArticleID": "C"}]
    vote(store, "B", "u1", 3)
    vote(store, "A", "u1", 5)
    out = [a["ArticleID"] for a in ranked(arts, store)]
    assert out == ["A", "B", "C"]


def test_vote_validation():
    from services.kb_rating import vote
    from utils.validators import ValidationError

    store = _store()
    for bad in (6, 0, "abc"):
        try:
            vote(store, "KB000001", "u1", bad)
        except ValidationError:
            continue
        raise AssertionError(f"невалидна оценка мора да е одбиена: {bad}")
    try:
        vote(store, "KB000001", "  ", 4)
    except ValidationError:
        pass
    else:
        raise AssertionError("празен корисник мора да е одбиен")
    assert store.records() == []


def test_vote_targets_one_row_instead_of_rewriting_the_table():
    from services.kb_rating import vote

    store = _store()
    vote(store, "KB000001", "u1", 4)
    vote(store, "KB000002", "u2", 2)

    def boom(*args, **kwargs):
        raise AssertionError("vote не смее да прави replace_all")

    store.replace_all = boom
    vote(store, "KB000001", "u1", 5)

    rows = {(r["ArticleID"], r["UserName"]): int(r["Score"]) for r in store.records()}
    assert rows == {("KB000001", "u1"): 5, ("KB000002", "u2"): 2}


def test_vote_rolls_back_when_audit_fails():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.kb_rating import vote
    from services.schemas import KB_RATING_COLS

    db = os.path.join(tempfile.mkdtemp(), "kbroll.db")
    store = DbStore(db, "kb_ratings", KB_RATING_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))
    vote(store, "KB000001", "u1", 4)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    history.log = boom
    try:
        vote(store, "KB000001", "u1", 1, history=history)
    except RuntimeError:
        pass
    else:
        raise AssertionError("падот на audit мора да се пренесе")

    assert int(store.records()[0]["Score"]) == 4
    assert history.store.records() == []


def test_vote_writes_audit_row():
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.kb_rating import vote
    from services.schemas import KB_RATING_COLS

    db = os.path.join(tempfile.mkdtemp(), "kbaudit.db")
    store = DbStore(db, "kb_ratings", KB_RATING_COLS)
    history = HistoryService(DbStore(db, "history", HISTORY_COLS))

    vote(store, "KB000001", "u1", 4, history=history, performed_by="ana")

    rows = history.store.records()
    assert [r["Action"] for r in rows] == ["KB_RATE"]
    assert rows[0]["AssetID"] == "KB000001"
    assert rows[0]["NewStatus"] == "4"
    assert rows[0]["PerformedBy"] == "ana"


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import KB_COLS, KB_RATING_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "kbu.db")
    monkeypatch.setattr(app_mod, "kb_articles", DbStore(db, "kb_articles", KB_COLS))
    monkeypatch.setattr(
        app_mod, "kb_ratings", DbStore(db, "kb_ratings", KB_RATING_COLS)
    )
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.kb_articles.append_row(
        {
            "ArticleID": "KB000001",
            "Title": "Принтер не печати",
            "Body": "Провери кабел.",
            "Tags": "",
            "Created": "2026-10-05 10:00",
            "Updated": "2026-10-05 10:00",
        }
    )
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_rate_route_stores_vote(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        r = c.post("/kb/KB000001/rate", data={"score": "5"})
        assert r.status_code == 302
        rows = app_mod.kb_ratings.records()
        assert len(rows) == 1
        assert int(rows[0]["Score"]) == 5
        c.post("/kb/KB000001/rate", data={"score": "3"})
        rows = app_mod.kb_ratings.records()
        assert len(rows) == 1
        assert int(rows[0]["Score"]) == 3

        c2 = app_mod.app.test_client()
        _login(c2, "cit")
        assert c2.post("/kb/KB000001/rate", data={"score": "5"}).status_code == 403
    finally:
        _wipe_users()


def test_detail_shows_average_and_form(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "mag")
        c.post("/kb/KB000001/rate", data={"score": "4"})
        body = c.get("/kb/KB000001").get_data(as_text=True)
        assert "Оценка" in body
        assert "4.0" in body or "4.5" in body
        assert re.search(r'name="score"', body)
    finally:
        _wipe_users()
