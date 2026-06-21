# Resident Newsletter — You said / We did (Tier 2: AI-assisted)

Reads the flash-survey free-text comments and the specials log, and produces a
draft **"You said / We did"** F&B section for the monthly resident newsletter:
the **themes residents raised** (the "you said") and the **facts of what the
kitchen offered** (the "we did", with dates), woven into a warm prose paragraph
that the **GM approves before the newsletter goes out**.

This is the last of the **Tier 2 (AI-assisted)** drafting tools; it copies the
reference pattern in `demo/feedback-theming`.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## The Tier 2 pattern — what the AI may and may not do

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

- **The "You said" themes are deterministic.** Which themes appear is decided by
  a case-insensitive keyword match over the survey comments (the same theming as
  `feedback-theming`). The keyword counts used to decide presence and order are
  computed by code in `build_resident_newsletter.py` and **never** pass through
  `draft_fn`.
- **The "We did" facts are deterministic.** The distinct specials offered in the
  period — deduped by dish name, sorted, each with its first-offered **date** —
  are read straight from `specials.csv`. The dates are factual text produced by
  code.
- **draft_fn drafts prose only.** It writes the newsletter paragraph around the
  themes and the dish **names** it is handed — never the dates. It is a
  pluggable function: a **deterministic template** here (`default_draft`), a
  **real model** in production — behind the *same interface*. Its signature
  (shared with the reference tool) is:

  ```python
  draft_fn(context: dict) -> str
  # context = {"you_said_themes": list[str],
  #            "sample_phrases": dict[str, list[str]],
  #            "we_did": list[str]}   # dish NAMES only — NO dates, NO numbers
  ```

  The context carries **dish names only — no dates, no counts, no numbers**, so
  a draft_fn — template or model — physically cannot change which themes appear
  or any date. The dated "We did" facts (`{dish, first_offered}`) are rendered
  **deterministically by code in `render()`, outside the draft**, so the GM
  still sees the dates — they just never pass through draft_fn. A test passes
  two different draft_fns and proves the `you_said_themes` and the dated
  `we_did_facts` are identical; a spy test proves **no string anywhere in the
  draft_fn context contains a digit**.
- **Nothing is auto-published.** `render()` badges the drafted section
  *"DRAFT — for GM approval before the newsletter goes out"*. The GM edits,
  approves and publishes.

## Run it

```bash
python3 build_resident_newsletter.py
```

Writes `resident-newsletter.html` in this folder.

## Test it

```bash
python3 -m unittest test_resident_newsletter
```

The tests confirm the present themes equal an independent keyword recompute,
prove that swapping `draft_fn` cannot change the themes or the dated we-did
facts, prove no string in the `draft_fn` context contains a digit (no date or
number reaches the draft) and the drafted prose carries no date, confirm
`total_comments` matches an independent comment count, confirm the GM-approval
badge is present, and guard against the committed HTML drifting from the
renderer.

Run the tests and the build script from inside the tool directory
(`demo/resident-newsletter/`) — all paths are relative to it.

## Production adoption

1. Replace the files in `sample-data/` with your real exports
   (`flash-survey.csv`, columns `date,food,service,value,comment`;
   `specials.csv`, columns `date,dish,description_seed,allergens`).
2. Edit the `themes` in `config.json` — each theme is a list of keywords; tune
   them to the language your residents actually use.
3. Optionally swap `draft_fn` for a real model behind the same
   `draft_fn(context) -> str` interface (context = present theme keys, sample
   phrases, and the we-did dish names — no dates, no counts).
4. Run `python3 build_resident_newsletter.py` and send the drafted section to
   the GM for approval before the newsletter goes out.

**Never change the deterministic path** (the keyword-theming and the
specials-deduping logic in `build_resident_newsletter.py` and the vendored
`benjamins_common.py`). The AI may draft the prose; it must never decide which
themes appear or alter a date. The same input must always produce the same
themes and facts; the tests depend on it.
