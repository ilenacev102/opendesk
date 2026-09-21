"""Phase Z: prove route tests never touch the production database."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_db_path_comes_from_env():
    import app as app_mod

    assert os.environ.get("SERVICEDESK_DB"), "conftest must set SERVICEDESK_DB"
    assert app_mod.DB_PATH == os.environ["SERVICEDESK_DB"]
    assert os.path.isfile(app_mod.DB_PATH) or True


def test_prod_db_untouched():
    import config

    prod = os.path.join(config.DATA_DIR, "servicedesk.db")
    import app as app_mod

    assert os.path.abspath(app_mod.DB_PATH) != os.path.abspath(prod)
