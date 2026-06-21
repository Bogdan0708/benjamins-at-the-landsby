"""Benjamin's at The Landsby — resident newsletter draft (Tier 2: AI-assisted).

Reads the flash-survey free-text comments and the specials log, and produces a
draft "You said / We did" F&B section for the monthly resident newsletter: the
THEMES residents raised (the "you said") and the FACTS of what the kitchen
offered (the "we did") — woven into a warm prose paragraph awaiting the GM's
approval before the newsletter goes out. It follows the reference Tier 2
division of labour exactly (see demo/feedback-theming):

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

  * The "You said" THEMES (which themes are present) and every factual DATE in
    the "We did" facts are computed by deterministic code below. The keyword
    counts used for ordering and the first-offered DATES are computed by code
    and NEVER pass through draft_fn, so a draft_fn cannot change which themes
    appear or any date.
  * draft_fn is a pluggable function that DRAFTS PROSE ONLY — the newsletter
    paragraph. In this demo it is a deterministic template (default_draft); in
    production a real model can swap in behind the SAME interface. It receives
    only qualitative context (theme keys, sample phrases, and the we-did dish
    NAMES — no dates, no counts, no numbers) and CANNOT see or alter which
    themes appear, any date, or any number. The dated "We did" facts are
    rendered deterministically by render(), outside the draft.
  * Nothing auto-publishes. render() badges the drafted section
    "DRAFT — for GM approval before the newsletter goes out". The GM edits,
    approves and publishes.

draft_fn signature (shared with the reference tool):
    draft_fn(context: dict) -> str
where context = {"you_said_themes": list[str], "sample_phrases": dict[str,list],
                 "we_did": list[str]}   -- dish NAMES only; NO dates, NO counts,
                 NO numbers.

Python standard library only. Same input always produces the same output.
"""
import html
import json
import sys
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())

SURVEY_EXPECTED = ["date", "food", "service", "value", "comment"]
SPECIALS_EXPECTED = ["date", "dish", "description_seed", "allergens"]


def _validate_survey(fn, row):
    # A row whose comment is empty/whitespace carries no free text to theme,
    # so it is skipped and counted. (No filename prefix: read_csv_rows prepends.)
    if not (row["comment"] or "").strip():
        raise bc.BenjaminsError("row has no comment")


def _validate_special(fn, row):
    # A special needs a dish name to be a "we did" fact; without one it is
    # skipped and counted.
    if not (row["dish"] or "").strip():
        raise bc.BenjaminsError("row missing special dish name")


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


def _join(items):
    """Deterministic 'a, b and c' join for a small list of strings."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# Human-readable label for each theme key, used only inside the prose.
_THEME_LABEL = {
    "service": "the warmth of our service",
    "food_quality": "the quality of our food",
    "soup_consistency": "the consistency of our soups",
}


def _theme_label(key):
    return _THEME_LABEL.get(key, key.replace("_", " "))


def default_draft(context):
    """Deterministic, pure draft_fn used for the demo.

    Weaves the present "you said" themes and the "we did" dish NAMES into a warm
    "You said / We did" newsletter paragraph. A production model can replace
    this behind the same interface; it must never receive or return a count or
    a date.

    The themes that appear and the first-offered dates of the we-did facts are
    fixed by deterministic code before this runs and rendered outside the draft;
    this function only writes prose around dish names and cannot change which
    themes appear or any date.
    """
    themes = context.get("you_said_themes") or []
    we_did = context.get("we_did") or []

    if themes:
        labels = [_theme_label(t) for t in themes]
        you_said = (
            "This month you told us how much you value "
            f"{_join(labels)}."
        )
    else:
        you_said = "This month you shared your thoughts on dining with us."

    if we_did:
        we_did_sentence = (
            f"Here is what we offered in return: across the period our kitchen "
            f"offered {_join(we_did)}. We will keep listening and keep cooking "
            "with the same care."
        )
    else:
        we_did_sentence = (
            "We will keep listening and keep cooking with the same care."
        )

    return f"You said: {you_said} {we_did_sentence}"


def compute(survey_path, specials_path, themes, draft_fn=default_draft):
    survey_rows, survey_skipped = bc.read_csv_rows(
        survey_path, SURVEY_EXPECTED, _validate_survey)
    spec_rows, spec_skipped = bc.read_csv_rows(
        specials_path, SPECIALS_EXPECTED, _validate_special)

    total_comments = len(survey_rows)

    # "You said": deterministic keyword theming over the comments. Counts are
    # used only to decide which themes are PRESENT and to order them; they are
    # NEVER passed to draft_fn.
    counts, sample_phrases = {}, {}
    for theme in themes:
        hits = _matches(theme, themes, survey_rows)
        counts[theme] = len(hits)
        seen, examples = set(), []
        for h in hits:
            if h not in seen:
                seen.add(h)
                examples.append(h)
            if len(examples) == 3:
                break
        sample_phrases[theme] = examples

    # Present themes, ordered most-mentioned first, ties broken by key — a
    # deterministic order. This is the "you said".
    you_said_themes = sorted(
        [t for t in themes if counts[t] > 0],
        key=lambda t: (-counts[t], t),
    )

    # "We did": the distinct specials offered in the period. First-seen date
    # wins; deduped by dish name; sorted by dish name for a deterministic order.
    # The dates are factual text produced by code and kept in a structured form
    # (we_did_facts) so render() can build the dated "We did" list deterministically.
    # The dates are NEVER handed to draft_fn — it only ever sees dish NAMES.
    first_seen = {}
    for r in spec_rows:
        dish = r["dish"].strip()
        if dish in first_seen:
            continue
        first_seen[dish] = (r["date"] or "").strip()
    we_did_facts = [
        {"dish": dish, "first_offered": (first_seen[dish] or None)}
        for dish in sorted(first_seen)
    ]
    # Dish NAMES only — no dates, no digits — for draft_fn's qualitative context.
    we_did_names = [f["dish"] for f in we_did_facts]

    # draft_fn sees ONLY qualitative context: the present theme keys, sample
    # phrases, and the dish NAMES (no dates, no counts, no numbers). The dated
    # facts are rendered deterministically by render(), never by draft_fn, so a
    # draft_fn cannot move a number, alter a date, or change which themes appear.
    context = {
        "you_said_themes": list(you_said_themes),
        "sample_phrases": {t: list(sample_phrases[t]) for t in you_said_themes},
        "we_did": list(we_did_names),
    }
    draft = draft_fn(context)

    return {
        "you_said_themes": you_said_themes,
        "we_did_facts": we_did_facts,
        "sample_phrases": {t: sample_phrases[t] for t in you_said_themes},
        "draft": draft,
        "total_comments": total_comments,
        "skipped": survey_skipped + spec_skipped,
    }


def render(metrics):
    esc = html.escape
    body = (
        "<h2>Resident newsletter &mdash; &ldquo;You said / We did&rdquo; section</h2>"
        "<p class=\"explain\">This F&amp;B section is <strong>AI-drafted from "
        "resident feedback</strong>. The <strong>themes you raised</strong> "
        "(&ldquo;you said&rdquo;) and the <strong>facts of what we offered</strong> "
        "(&ldquo;we did&rdquo;, including dates) are <strong>computed by code</strong> "
        "&mdash; the AI never sees or changes which themes appear or any date. The "
        "AI only drafts the surrounding prose. <strong>Nothing is published "
        "automatically:</strong> the GM approves the section before the newsletter "
        "goes out.</p>"
        f"<p class=\"explain\">Drafted from {metrics['total_comments']} resident "
        f"comments this period.</p>"
    )

    # Deterministic "You said" themes.
    body += "<h2 class=\"sec\">You said &mdash; themes (computed by code)</h2>"
    if metrics["you_said_themes"]:
        body += "<div class=\"themes\">"
        for theme in metrics["you_said_themes"]:
            phrases = metrics["sample_phrases"].get(theme, [])
            phrase_html = "".join(
                f"<li>{esc(p)}</li>" for p in phrases) or "<li>(none)</li>"
            body += (
                "<section class=\"theme\">"
                f"<div class=\"key\">theme: <code>{esc(theme)}</code></div>"
                f"<div class=\"phrases\">Sample phrases:<ul>{phrase_html}</ul></div>"
                "</section>"
            )
        body += "</div>"
    else:
        body += "<p class=\"explain\">No themes present this period.</p>"

    # Deterministic "We did" facts — dish names with their first-offered dates,
    # rendered here by code (never by draft_fn).
    body += "<h2 class=\"sec\">We did &mdash; facts (computed by code)</h2>"
    items = []
    for fact in metrics["we_did_facts"]:
        if fact["first_offered"]:
            items.append(
                f"<li>{esc(fact['dish'])} (first offered "
                f"{esc(fact['first_offered'])})</li>"
            )
        else:
            items.append(f"<li>{esc(fact['dish'])}</li>")
    we_did_html = "".join(items) or "<li>(none)</li>"
    body += f"<ul class=\"wedid\">{we_did_html}</ul>"

    # The AI-drafted prose, badged for GM approval.
    body += "<h2 class=\"sec\">Drafted newsletter section</h2>"
    body += (
        "<div class=\"draftwrap\">"
        "<div class=\"badge\">DRAFT &mdash; for GM approval before the "
        "newsletter goes out</div>"
        f"<div class=\"draft\">{esc(metrics['draft'])}</div>"
        "</div>"
    )

    body += (
        "<style>"
        ".explain{font:13px sans-serif;color:#444;}"
        ".sec{margin-top:18px;}"
        ".themes{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-top:8px;}"
        ".theme{border:1px solid #ccc;border-radius:5px;padding:10px;}"
        ".key{font:11px sans-serif;color:#777;}"
        ".phrases{font:12px sans-serif;color:#444;margin-top:6px;}"
        ".wedid{font:13px sans-serif;color:#222;}"
        ".draftwrap{background:#f7f9f7;border:1px dashed #b8860b;border-radius:4px;"
        "padding:10px;margin-top:8px;}"
        ".badge{font:10px sans-serif;text-transform:uppercase;letter-spacing:.04em;"
        "background:#fff3cd;border:1px solid #b8860b;color:#7a5800;border-radius:3px;"
        "padding:2px 6px;display:inline-block;}"
        ".draft{font:14px/1.6 Georgia,serif;color:#222;margin-top:8px;}"
        "</style>"
    )

    return bc.page("Resident Newsletter", CONFIG["site_name"], body,
                   metrics["skipped"], "monthly You-said/We-did F&B section")


def main():
    try:
        html_out = render(compute("sample-data/flash-survey.csv",
                                  "sample-data/specials.csv",
                                  CONFIG["themes"]))
    except bc.BenjaminsError as e:
        print(f"Could not build the resident-newsletter page: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("resident-newsletter.html").write_text(html_out)
    print("Wrote resident-newsletter.html")


if __name__ == "__main__":
    main()
