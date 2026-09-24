"""Enterprise Wave2 todo 13: shared rate-limit abstraction (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_file_limiter_shared_across_instances():
    from services.ratelimit import FileLimiter

    path = os.path.join(tempfile.mkdtemp(), "rl.json")
    worker_a = FileLimiter(path)
    worker_b = FileLimiter(path)
    assert worker_a.is_allowed("k", 2, 60, now=1000.0) is True
    assert worker_b.is_allowed("k", 2, 60, now=1001.0) is True
    assert worker_a.is_allowed("k", 2, 60, now=1002.0) is False
    assert worker_b.is_allowed("other", 2, 60, now=1002.0) is True


def test_file_limiter_window_slides():
    from services.ratelimit import FileLimiter

    path = os.path.join(tempfile.mkdtemp(), "rl.json")
    limiter = FileLimiter(path)
    assert limiter.is_allowed("k", 1, 60, now=1000.0) is True
    assert limiter.is_allowed("k", 1, 60, now=1030.0) is False
    assert limiter.is_allowed("k", 1, 60, now=1061.0) is True


def test_file_limiter_corrupt_file_falls_back():
    from services.ratelimit import FileLimiter

    path = os.path.join(tempfile.mkdtemp(), "rl.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not-json!!!")
    limiter = FileLimiter(path)
    assert limiter.is_allowed("k", 1, 60, now=1000.0) is True


def test_file_limiter_reset():
    from services.ratelimit import FileLimiter

    path = os.path.join(tempfile.mkdtemp(), "rl.json")
    limiter = FileLimiter(path)
    assert limiter.is_allowed("k", 1, 60, now=1000.0) is True
    limiter.reset()
    assert limiter.is_allowed("k", 1, 60, now=1001.0) is True


def test_factory_selects_backend(monkeypatch, tmp_path):
    from services.ratelimit import FileLimiter, MemoryLimiter, get_limiter

    monkeypatch.delenv("SERVICEDESK_RATELIMIT", raising=False)
    assert isinstance(get_limiter(), MemoryLimiter)
    target = str(tmp_path / "shared.json")
    monkeypatch.setenv("SERVICEDESK_RATELIMIT", "file")
    monkeypatch.setenv("SERVICEDESK_RATELIMIT_FILE", target)
    limiter = get_limiter()
    assert isinstance(limiter, FileLimiter)
    assert limiter.path == target


def test_upload_limit_25mb():
    import app as app_mod

    assert app_mod.app.config["MAX_CONTENT_LENGTH"] == 25 * 1024 * 1024
