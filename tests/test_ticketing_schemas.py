"""Ticketing Pro todo 1: SLA/KB/comments schemas + LinkedTo migration."""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_new_cols_defined():
    from services.schemas import COMMENT_COLS, KB_COLS, KB_LINK_COLS
    from services.schemas import SLA_POLICY_COLS

    assert "PolicyID" in SLA_POLICY_COLS and "BreachHours" in SLA_POLICY_COLS
    assert "ArticleID" in KB_COLS and "Title" in KB_COLS
    assert "CommentID" in COMMENT_COLS and "IncidentID" in COMMENT_COLS
    assert "ArticleID" in KB_LINK_COLS and "IncidentID" in KB_LINK_COLS


def test_linkedto_in_incident_cols():
    from services.schemas import INCIDENT_COLS

    assert "LinkedTo" in INCIDENT_COLS


def test_stores_wired():
    import app as app_mod
    from services.schemas import COMMENT_COLS, KB_COLS, KB_LINK_COLS
    from services.schemas import SLA_POLICY_COLS

    assert app_mod.sla_policies.columns == SLA_POLICY_COLS
    assert app_mod.kb_articles.columns == KB_COLS
    assert app_mod.comments.columns == COMMENT_COLS
    assert app_mod.kb_links.columns == KB_LINK_COLS


def test_legacy_incidents_gain_linkedto():
    from services.db_service import DbStore
    from services.schemas import INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "legacy_inc.db")
    con = sqlite3.connect(db)
    con.execute(
        'CREATE TABLE "incidents" ("IncidentID" TEXT, "Title" TEXT, "Status" TEXT)'
    )
    con.execute("INSERT INTO \"incidents\" VALUES ('I000001', 'x', 'open')")
    con.commit()
    con.close()
    store = DbStore(db, "incidents", INCIDENT_COLS)
    row = store.find("IncidentID", "I000001")
    assert row is not None
    assert row["Title"] == "x"
    assert row["LinkedTo"] == ""
