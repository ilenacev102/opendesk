"""P2.3: rate-limit prefixes match path segments, not arbitrary substrings."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_api_prefix_requires_segment_boundary():
    from app import _rate_bucket

    assert _rate_bucket("/api/v1") == "/api/v1"
    assert _rate_bucket("/api/v1/devices") == "/api/v1"
    assert _rate_bucket("/api/v1foo") is None
    assert _rate_bucket("/api/v2/devices") is None


def test_login_prefix_is_exact():
    from app import _rate_bucket

    assert _rate_bucket("/login") == "/login"
    assert _rate_bucket("/loginx") is None
    assert _rate_bucket("/login/extra") == "/login"


def test_pdf_prefix_matches_only_its_subtree():
    from app import _rate_bucket

    assert _rate_bucket("/pdf") == "/pdf"
    assert _rate_bucket("/pdf/report.pdf") == "/pdf"
    assert _rate_bucket("/pdfx") is None


def test_unknown_path_is_not_limited():
    from app import _rate_bucket

    assert _rate_bucket("/devices") is None
    assert _rate_bucket("") is None
