"""Phase Z: route tests run against an isolated DB, never data/servicedesk.db."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="servicedesk-test-")
os.environ["SERVICEDESK_DB"] = os.path.join(_tmp, "test.db")
os.environ.setdefault("SERVICEDESK_CSRF", "0")
