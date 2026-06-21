# Feedback Theming (reference Tier 2: AI-assisted)

Reads the flash-survey free-text comments, groups them into **themes** by
keyword, and produces a one-page **review queue**: each theme shows a
deterministic count, sample phrases, and an AI-**suggested** display label that
a person approves before use.

This is the reference for the **Tier 2 (AI-assisted)** pattern that the sibling
tools copy.

## Sample data is synthetic

Everything in `sample-data/` is **synthetic, for demonstration only**. The page
carries a "SAMPLE DATA" watermark. No real Benjamin's figures are used.

## The Tier 2 pattern — what the AI may and may not do

    deterministic data work  ->  draft_fn(context)  ->  review queue  ->  human

- **Counts are deterministic.** Every number on the page is computed by code in
  `build_feedback_theming.py` — a case-insensitive keyword match over the
  comments. `compute()` recounts in a second pass (`_independent`) and a test
  asserts the two agree.
- **draft_fn drafts prose only.** It suggests a short display *label* for each
  theme. It is a pluggable function: a **deterministic template** here
  (`default_draft`), a **real model** in production — behind the *same
  interface*. Its signature (siblings reuse this shape) is:

  ```python
  draft_fn(context: dict) -> str
  # context = {"theme_key": str, "sample_phrases": list[str]}   # NO counts
  ```

  The context contains **no counts and no numbers**, so a draft_fn — template or
  model — physically cannot move a figure. A test passes two different draft_fns
  and proves the counts are identical, and a spy test proves the context handed
  to draft_fn carries no numbers.
- **Nothing is auto-published.** `render()` is a review queue: every suggested
  label is marked *"suggested label — pending approval"* beside its
  code-computed count. A person approves a label before it is used anywhere.

## Run it

```bash
python3 build_feedback_theming.py
```

Writes `feedback-theming.html` in this folder.

## Test it

```bash
python3 -m unittest test_feedback_theming
```

The tests confirm the counts equal an independent keyword recount, prove that
swapping `draft_fn` cannot change any count, prove `draft_fn` receives no
numbers, confirm `total_comments` matches an independent comment count, and
guard against the committed HTML drifting from the renderer.

Run the tests and the build script from inside the tool directory
(`demo/feedback-theming/`) — all paths are relative to it.

## Production adoption

1. Replace the files in `sample-data/` with your real survey export
   (`flash-survey.csv`, columns `date,food,service,value,comment`).
2. Edit the `themes` in `config.json` — each theme is a list of keywords;
   tune them to the language your residents actually use.
3. Optionally swap `draft_fn` for a real model behind the same
   `draft_fn(context) -> str` interface (context = theme key + sample phrases,
   no counts).
4. Run `python3 build_feedback_theming.py` and review the queue.

**Never change the deterministic count path** (the keyword-matching and
counting logic in `build_feedback_theming.py` and the vendored
`benjamins_common.py`). The AI may suggest labels; it must never touch a number.
The same input must always produce the same counts; the tests depend on it.
