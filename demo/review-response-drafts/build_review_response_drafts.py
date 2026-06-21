"""Benjamin's at The Landsby — review-response drafts (Tier 2: AI-assisted).

Reads the public-review export (OpenTable, TripAdvisor, Google) and produces a
one-page REVIEW QUEUE: for every review it shows the star rating, the original
text, and a house-voice reply DRAFT awaiting a person's approval. It follows the
reference Tier 2 division of labour exactly (see demo/feedback-theming):

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

  * EVERY NUMBER is computed by deterministic code below. Each review is bucketed
    by its rating — negative (1-2), neutral (3), positive (4-5) — purely from the
    rating integer. The bucket counts are the source of truth and never pass
    through draft_fn.
  * draft_fn is a pluggable function that DRAFTS PROSE ONLY — a reply for each
    review. In this demo it is a deterministic template (default_draft); in
    production a real model can swap in behind the SAME interface. It receives
    only qualitative context (platform + bucket + optional keyword themes) and
    CANNOT see or alter any rating number or count.
  * Nothing is auto-published. render() produces a review queue: each draft reply
    is badged "DRAFT — pending approval, not sent". A person edits, approves, and
    posts replies.

draft_fn signature (shared with the reference tool):
    draft_fn(context: dict) -> str
where context = {"platform": str, "bucket": str, "themes": list[str]}  -- NO
numbers (no rating, no counts).

Python standard library only. Same input always produces the same output.
"""
import html
import json
import sys
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
EXPECTED = ["date", "platform", "rating", "text"]

# Marker text the default negative template always contains. Tests assert on it
# so a one-star review demonstrably routes to the apology/repair template.
NEGATIVE_MARKER = "we're sorry"

# Deterministic keyword -> theme tag map. Used only to give draft_fn qualitative
# flavour; themes are strings and carry NO numbers.
_THEME_KEYWORDS = {
    "service": ["staff", "service", "looked after", "attentive", "welcome", "unhurried"],
    "food": ["food", "meal", "lunch", "soup", "tasty", "presented", "salty"],
    "value": ["value", "price", "expensive", "worth"],
}


def _bucket(rating):
    """Deterministic rating -> bucket. rating is a validated int 1..5."""
    if rating in (1, 2):
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


def _themes(text):
    """Deterministic, ordered keyword tags derived from the review text.

    Returns a list of theme strings (no numbers). Order is the fixed map order so
    the result is deterministic for the same text.
    """
    low = (text or "").lower()
    tags = []
    for theme, kws in _THEME_KEYWORDS.items():
        if any(k in low for k in kws):
            tags.append(theme)
    return tags


def _validate(fn, row):
    # A review with no platform cannot be replied to on the right channel; a
    # rating that is not an integer 1-5 cannot be bucketed. Either is skipped and
    # counted in the data-quality footer. (No filename prefix here:
    # bc.read_csv_rows already prepends filename + line.)
    if not (row["platform"] or "").strip():
        raise bc.BenjaminsError("row missing platform")
    raw = (row["rating"] or "").strip()
    try:
        rating = int(raw)
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"rating is not an integer 1-5: {row['rating']!r}")
    if rating < 1 or rating > 5:
        raise bc.BenjaminsError(f"rating out of range 1-5: {rating}")


def default_draft(context):
    """Deterministic, pure draft_fn used for the demo.

    Produces a house-voice reply DRAFT keyed on the bucket. A production model can
    replace this behind the same interface; it must never receive or return a
    rating or count.
    """
    bucket = context["bucket"]
    platform = context["platform"]
    themes = context.get("themes") or []
    signoff = CONFIG.get("signoff", "The team at Benjamin's")
    theme_phrase = ""
    if themes:
        theme_phrase = f" Your note on {_join(themes)} is noted and shared with the team."

    if bucket == "negative":
        body = (
            f"Thank you for taking the time to write, and {NEGATIVE_MARKER} your visit "
            f"fell short of the welcome we want every guest to feel."
            f"{theme_phrase} We'd genuinely value the chance to put it right — please ask "
            f"for the manager on your next visit, or contact us directly."
        )
    elif bucket == "neutral":
        body = (
            f"Thank you for your honest feedback and for dining with us."
            f"{theme_phrase} We'd love the opportunity to show you a warmer, fuller "
            f"experience next time — do let us know when you're planning to return so we "
            f"can look after you properly."
        )
    else:  # positive
        body = (
            f"Thank you so much for your kind words — they mean a great deal to the "
            f"whole team.{theme_phrase} We look forward to welcoming you back to "
            f"Benjamin's very soon."
        )
    return f"{body}\n\nWith warm regards,\n{signoff} (via {platform})"


def _join(items):
    """Deterministic 'a, b and c' join for a small list of strings."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def compute(reviews_path, draft_fn=default_draft):
    rows, skipped = bc.read_csv_rows(reviews_path, EXPECTED, _validate)

    # Deterministic display order: by date then platform (then text to fully
    # stabilise duplicate (date, platform) pairs).
    rows = sorted(rows, key=lambda r: (r["date"], r["platform"], r["text"]))

    bucket_counts = {"negative": 0, "neutral": 0, "positive": 0}
    reviews = []
    for r in rows:
        rating = int(r["rating"])          # validated as int 1-5
        bucket = _bucket(rating)           # deterministic from the rating
        bucket_counts[bucket] += 1

        # draft_fn sees ONLY qualitative context: platform, bucket, theme tags.
        # No rating number and no count is ever placed in this context, so a
        # draft_fn — template or model — physically cannot move a number.
        context = {
            "platform": r["platform"],
            "bucket": bucket,
            "themes": _themes(r["text"]),
        }
        draft = draft_fn(context)

        reviews.append({
            "date": r["date"],
            "platform": r["platform"],
            "rating": rating,
            "text": r["text"],
            "bucket": bucket,
            "draft": draft,
        })

    return {
        "reviews": reviews,
        "bucket_counts": bucket_counts,
        "total_reviews": len(reviews),
        "skipped": skipped,
    }


_BUCKET_LABEL = {
    "negative": "Needs repair (1–2★)",
    "neutral": "Lukewarm (3★)",
    "positive": "Happy (4–5★)",
}


def render(metrics):
    esc = html.escape
    bc_counts = metrics["bucket_counts"]
    body = (
        "<h2>Review reply drafts &mdash; approval queue</h2>"
        "<p class=\"explain\">Each public review is sorted into a band by its "
        "<strong>star rating, computed by code</strong> (1&ndash;2 = needs repair, "
        "3 = lukewarm, 4&ndash;5 = happy). The <strong>reply below each review is an "
        "AI draft</strong>, written from the platform and band only &mdash; the AI "
        "never sees or changes a rating. <strong>Nothing is sent automatically:</strong> "
        "a person edits, approves and posts each reply.</p>"
        f"<p class=\"explain\">{metrics['total_reviews']} reviews in the queue.</p>"
    )

    body += "<div class=\"summary\">"
    for bucket in ("negative", "neutral", "positive"):
        body += (
            f"<div class=\"sumcell {bucket}\">"
            f"<div class=\"sumcount\">{bc_counts[bucket]}</div>"
            f"<div class=\"sumlabel\">{esc(_BUCKET_LABEL[bucket])} "
            f"<span class=\"tag\">count computed by code</span></div>"
            "</div>"
        )
    body += "</div>"

    body += "<div class=\"queue\">"
    for rec in metrics["reviews"]:
        stars = "&#9733;" * rec["rating"] + "&#9734;" * (5 - rec["rating"])
        body += (
            f"<section class=\"card {rec['bucket']}\">"
            "<div class=\"meta\">"
            f"<span class=\"platform\">{esc(rec['platform'])}</span>"
            f"<span class=\"date\">{esc(rec['date'])}</span>"
            f"<span class=\"stars\" title=\"rating computed by code\">{stars} "
            f"<span class=\"ratingnum\">{rec['rating']}/5</span></span>"
            "</div>"
            f"<blockquote class=\"reviewtext\">{esc(rec['text'])}</blockquote>"
            "<div class=\"draftwrap\">"
            "<div class=\"badge\">DRAFT &mdash; pending approval, not sent</div>"
            f"<div class=\"draft\">{esc(rec['draft'])}</div>"
            "</div>"
            "</section>"
        )
    body += "</div>"

    body += (
        "<style>"
        ".explain{font:13px sans-serif;color:#444;}"
        ".summary{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:14px 0;}"
        ".sumcell{border:1px solid #ccc;border-radius:5px;padding:10px;}"
        ".sumcell.negative{border-left:4px solid #a33;}"
        ".sumcell.neutral{border-left:4px solid #b8860b;}"
        ".sumcell.positive{border-left:4px solid #1f3a2d;}"
        ".sumcount{font-size:26px;color:#1f3a2d;}"
        ".sumlabel{font:11px sans-serif;color:#555;}"
        ".tag{font:10px sans-serif;color:#555;background:#eef3ef;border-radius:3px;padding:1px 5px;}"
        ".queue{display:grid;gap:12px;margin-top:8px;}"
        ".card{border:1px solid #ccc;border-radius:5px;padding:12px;}"
        ".card.negative{border-left:4px solid #a33;}"
        ".card.neutral{border-left:4px solid #b8860b;}"
        ".card.positive{border-left:4px solid #1f3a2d;}"
        ".meta{display:flex;gap:12px;align-items:baseline;font:12px sans-serif;color:#555;}"
        ".platform{text-transform:capitalize;font-weight:bold;color:#1f3a2d;}"
        ".stars{margin-left:auto;color:#b8860b;font-size:14px;}"
        ".ratingnum{font:11px sans-serif;color:#555;}"
        ".reviewtext{margin:8px 0;font-style:italic;color:#222;border-left:2px solid #ddd;"
        "padding-left:10px;}"
        ".draftwrap{background:#f7f9f7;border:1px dashed #b8860b;border-radius:4px;padding:8px;}"
        ".badge{font:10px sans-serif;text-transform:uppercase;letter-spacing:.04em;"
        "background:#fff3cd;border:1px solid #b8860b;color:#7a5800;border-radius:3px;"
        "padding:2px 6px;display:inline-block;}"
        ".draft{font:13px/1.5 Georgia,serif;color:#222;margin-top:6px;white-space:pre-wrap;}"
        "</style>"
    )

    return bc.page("Review Response Drafts", CONFIG["site_name"], body,
                   metrics["skipped"], "public-review reply queue")


def main():
    try:
        html_out = render(compute("sample-data/reviews.csv"))
    except bc.BenjaminsError as e:
        print(f"Could not build the review-response drafts page: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("review-response-drafts.html").write_text(html_out)
    print("Wrote review-response-drafts.html")


if __name__ == "__main__":
    main()
