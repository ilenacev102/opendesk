"""Phase B.2: linear depreciation for bookkeeping reports."""

import datetime


def book_value(price_raw, purchase_raw, years: int = 4):
    """Current book value or None when inputs are unusable."""
    try:
        price = float(str(price_raw or "").strip().replace(",", "."))
    except ValueError:
        return None
    try:
        bought = datetime.date.fromisoformat(str(purchase_raw or "").strip()[:10])
    except ValueError:
        return None
    age_days = (datetime.date.today() - bought).days
    if age_days < 0:
        return round(price, 2)
    frac = age_days / (years * 365)
    return round(max(0.0, price * (1.0 - frac)), 2)
