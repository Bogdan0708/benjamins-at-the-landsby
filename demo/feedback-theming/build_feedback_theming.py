"""Benjamin's at The Landsby — feedback theming (reference Tier 2 tool).

Reads the flash-survey free-text comments and groups them into THEMES by
keyword. This is the reference for the Tier 2 (AI-assisted) pattern that the
sibling tools copy, so the division of labour is deliberate and strict:

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

  * EVERY NUMBER is computed by deterministic code below. The keyword counts
    are the source of truth and never pass through draft_fn.
  * draft_fn is a pluggable function that DRAFTS PROSE ONLY — a short display
    label for each theme. In this demo it is a deterministic template
    (default_draft); in production a real model can swap in behind the SAME
    interface. It receives only qualitative context (theme key + a few sample
    phrases) and CANNOT see or alter any count.
  * Nothing is auto-published. render() produces a review queue: the suggested
    labels are shown as PENDING human approval beside the deterministic counts.

draft_fn signature (siblings reuse this shape):
    draft_fn(context: dict) -> str
where context = {"theme_key": str, "sample_phrases": list[str]}  -- NO counts.

Python standard library only. Same input always produces the same output.
"""
import html
import json
import sys
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
EXPECTED = ["date", "food", "service", "value", "comment"]


def _validate(fn, row):
    # A row whose comment is empty/whitespace carries no free text to theme,
    # so it is skipped and counted in the data-quality footer.
    if not (row["comment"] or "").strip():
        raise bc.BenjaminsError("row has no comment")


def default_draft(context):
    """Deterministic, pure draft_fn used for the demo.

    Turns the theme key into a human-readable label, appended with one sample
    phrase for flavour when available. A production model can replace this
    behind the same interface; it must never receive or return a count.
    """
    key = context["theme_key"]
    label = key.replace("_", " ").title()
    phrases = context.get("sample_phrases") or []
    if phrases:
        return f"{label} — e.g. “{phrases[0]}”"
    return label


def _matches(theme_key, themes, rows):
    """Comments (case-insensitive substring) matching any keyword of a theme."""
    kws = themes[theme_key]
    hits = []
    for r in rows:
        com = r["comment"].strip()
        low = com.lower()
        if any(k in low for k in kws):
            hits.append(com)
    return hits


def compute(survey_path, themes, draft_fn=default_draft):
    rows, skipped = bc.read_csv_rows(survey_path, EXPECTED, _validate)
    total_comments = len(rows)

    counts, sample_phrases = {}, {}
    for theme in themes:
        hits = _matches(theme, themes, rows)
        counts[theme] = len(hits)
        # Up to 3 distinct example snippets, in first-seen order (deterministic).
        seen, examples = set(), []
        for h in hits:
            if h not in seen:
                seen.add(h)
                examples.append(h)
            if len(examples) == 3:
                break
        sample_phrases[theme] = examples

    # Independent second pass over the same valid rows. The test asserts this
    # equals `counts`; it guards the count path against accidental change.
    independent = {theme: len(_matches(theme, themes, rows)) for theme in themes}

    # draft_fn sees ONLY qualitative context: the theme key and sample phrases.
    # No count is ever placed in this context, so a draft_fn cannot move a number.
    labels = {}
    for theme in themes:
        context = {"theme_key": theme, "sample_phrases": list(sample_phrases[theme])}
        labels[theme] = draft_fn(context)

    return {
        "counts": counts,
        "labels": labels,
        "sample_phrases": sample_phrases,
        "_independent": independent,
        "skipped": skipped,
        "total_comments": total_comments,
    }


def render(metrics):
    esc = html.escape
    body = (
        "<h2>Resident feedback themes &mdash; review queue</h2>"
        "<p class=\"explain\">Theme <strong>counts are computed by code</strong> "
        "(keyword matches over the survey comments). The <strong>labels are AI "
        "suggestions</strong> drafted from sample phrases only &mdash; the AI never "
        "sees or changes a number. Each label is shown <strong>pending a person's "
        "approval</strong> before it is used anywhere.</p>"
        f"<p class=\"explain\">{metrics['total_comments']} comments themed across "
        f"{len(metrics['counts'])} themes.</p>"
    )

    # Stable display order: most-mentioned theme first, ties broken by key.
    order = sorted(metrics["counts"], key=lambda t: (-metrics["counts"][t], t))
    body += "<div class=\"themes\">"
    for theme in order:
        count = metrics["counts"][theme]
        label = metrics["labels"][theme]
        phrases = metrics["sample_phrases"][theme]
        phrase_html = "".join(f"<li>{esc(p)}</li>" for p in phrases) or "<li>(none)</li>"
        body += (
            "<section class=\"theme\">"
            f"<div class=\"suggested\">Suggested label &mdash; pending approval</div>"
            f"<div class=\"label\">{esc(label)}</div>"
            f"<div class=\"count\">{count} comment(s) "
            f"<span class=\"tag\">count computed by code</span></div>"
            f"<div class=\"key\">theme key: <code>{esc(theme)}</code></div>"
            f"<div class=\"phrases\">Sample phrases:<ul>{phrase_html}</ul></div>"
            "</section>"
        )
    body += "</div>"
    body += (
        "<style>"
        ".explain{font:13px sans-serif;color:#444;}"
        ".themes{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-top:14px;}"
        ".theme{border:1px solid #ccc;border-radius:5px;padding:10px;}"
        ".suggested{font:10px sans-serif;text-transform:uppercase;letter-spacing:.04em;"
        "background:#fff3cd;border:1px solid #b8860b;color:#7a5800;border-radius:3px;"
        "padding:2px 6px;display:inline-block;}"
        ".label{font-size:16px;color:#1f3a2d;margin:8px 0 4px;}"
        ".count{font:13px sans-serif;color:#222;}"
        ".tag{font:10px sans-serif;color:#555;background:#eef3ef;border-radius:3px;padding:1px 5px;}"
        ".key{font:11px sans-serif;color:#777;margin-top:4px;}"
        ".phrases{font:12px sans-serif;color:#444;margin-top:6px;}"
        "</style>"
    )

    return bc.page("Feedback Theming", CONFIG["site_name"], body,
                   metrics["skipped"], "resident feedback review queue")


def main():
    try:
        html_out = render(compute("sample-data/flash-survey.csv", CONFIG["themes"]))
    except bc.BenjaminsError as e:
        print(f"Could not build the feedback theming page: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("feedback-theming.html").write_text(html_out)
    print("Wrote feedback-theming.html")


if __name__ == "__main__":
    main()
