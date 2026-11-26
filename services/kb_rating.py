"""KB article ratings (F5): 1-5 votes, one row per user, ranking helpers."""

from utils.validators import ValidationError


def vote(store, article_id, username, score, *, history=None, performed_by="admin"):
    """Record the user's 1-5 score for an article (upsert per user).

    Returns the stored row. Blank article/user and out-of-range scores raise
    ValidationError. Only the caller's row is touched, inside one transaction,
    so concurrent votes never overwrite each other.
    """
    article_id = (article_id or "").strip()
    username = (username or "").strip()
    if not article_id:
        raise ValidationError("Написот е задолжителен.")
    if not username:
        raise ValidationError("Корисникот е задолжителен.")
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise ValidationError(f"Невалидна оценка: {score}.")
    if not 1 <= score <= 5:
        raise ValidationError(f"Оцената мора да е од 1 до 5: {score}.")

    from services.db_service import store_transaction

    live = [store]
    if history is not None and getattr(history, "store", None) is not None:
        live.append(history.store)
    with store_transaction(*live) as con:
        changed = store.update_where_all(
            {"ArticleID": article_id, "UserName": username},
            {"Score": str(score)},
            con=con,
        )
        row = {"ArticleID": article_id, "UserName": username, "Score": str(score)}
        if not changed:
            store.append_row(row, con=con)
        if history is not None:
            history.log(
                "KB_RATE",
                article_id,
                "",
                str(score),
                "",
                "",
                "",
                username,
                performed_by,
                "",
                con=con,
            )
    return row


def average(store, article_id):
    """Mean score for the article rounded to 2 decimals; None when unrated."""
    total = 0
    count = 0
    for r in store.records():
        if r.get("ArticleID") != article_id:
            continue
        try:
            total += int(r.get("Score", ""))
        except (TypeError, ValueError):
            continue
        count += 1
    if not count:
        return None
    return round(total / count, 2)


def ranked(articles, store):
    """Stable sort: rated first (higher average first), unrated last."""
    sums = {}
    counts = {}
    for r in store.records():
        aid = r.get("ArticleID", "")
        try:
            s = int(r.get("Score", ""))
        except (TypeError, ValueError):
            continue
        sums[aid] = sums.get(aid, 0) + s
        counts[aid] = counts.get(aid, 0) + 1

    def key(article):
        aid = article.get("ArticleID", "")
        if not counts.get(aid):
            return (1, 0.0)
        return (0, -(sums[aid] / counts[aid]))

    return sorted(articles, key=key)
