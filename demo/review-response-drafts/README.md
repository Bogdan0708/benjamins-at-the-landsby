# Review Response Drafts (Tier 2: AI-assisted)

Reads the public-review export (OpenTable, TripAdvisor, Google) and produces a
one-page **approval queue**: every review is sorted into a band by its star
rating, and beneath each one sits a house-voice reply **draft** that a person
edits, approves and posts. Nothing is sent automatically.

This tool follows the **Tier 2 (AI-assisted)** pattern set by the reference tool
`demo/feedback-theming`.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## The Tier 2 pattern — what the AI may and may not do

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

- **Bucketing is deterministic.** Each review is placed in a band purely from its
  rating integer — negative (1–2★), neutral (3★), positive (4–5★) — by code in
  `build_review_response_drafts.py`. The bucket counts are the source of truth.
- **draft_fn drafts prose only.** It writes the reply for each review. It is a
  pluggable function: a **deterministic template** here (`default_draft`), a
  **real model** in production — behind the *same interface*. Its signature
  (shared with the reference tool) is:

  ```python
  draft_fn(context: dict) -> str
  # context = {"platform": str, "bucket": str, "themes": list[str]}   # NO numbers
  ```

  The context contains **no rating number and no counts**, so a draft_fn —
  template or model — physically cannot move a figure or re-band a review. A test
  passes two different draft_fns and proves the bucket counts AND the per-review
  rating values are identical; a spy test proves the context handed to draft_fn
  carries no numbers.
- **Nothing is auto-published.** `render()` is a review queue: every draft reply
  is badged *"DRAFT — pending approval, not sent"* beside the code-computed star
  rating. A person edits, approves and posts each reply.

## Run it

```bash
python3 build_review_response_drafts.py
```

Writes `review-response-drafts.html` in this folder.

## Test it

```bash
python3 -m unittest test_review_response_drafts
```

The tests confirm the bucket counts equal an independent recount from the raw
ratings, prove that swapping `draft_fn` cannot change any bucket count or rating,
prove `draft_fn` receives no numbers, confirm a one-star review routes to the
negative (apology/repair) template, confirm malformed rows are skipped and
counted, and guard against the committed HTML drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/review-response-drafts/`) — all paths are relative to it.

## Production adoption

1. Replace `sample-data/reviews.csv` with your real review export (columns
   `date,platform,rating,text`).
2. Optionally tune the house voice in `config.json` (`signoff`) and the keyword
   theme map at the top of `build_review_response_drafts.py`.
3. Optionally swap `draft_fn` for a real model behind the same
   `draft_fn(context) -> str` interface (context = platform + bucket + theme
   tags, no numbers).
4. Run `python3 build_review_response_drafts.py` and work the queue: edit,
   approve and post each reply yourself.

**Never change the deterministic numeric/bucket path** (the rating validation,
bucketing and counting logic in `build_review_response_drafts.py` and the
vendored `benjamins_common.py`). The AI may draft the words of a reply; it must
never touch a rating or a count. The same input must always produce the same
buckets and counts; the tests depend on it.
