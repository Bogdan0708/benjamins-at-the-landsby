# Benjamin's at The Landsby — Automation Portfolio

**Companion to the Restaurant Manager Plan (Pillar 5: data-driven decision making)**

Prepared by: Vasile Bogdan Godja — candidate, Restaurant Manager
Date: June 2026

---

## Why this document

Pillar 5 of the plan commits to extracting full value from the systems the group already runs — Cubigo, Apicbase, Monika, Square and our OpenTable listing — supported by internal tools I would build personally, at no software cost. This catalogue sets out exactly what those tools are, what each one reads and produces, the estimated build effort, and when each lands against the 90-day plan.

Working demonstrations of all thirteen tools are available on request — each built on clearly labelled synthetic sample data, each a self-contained folder that turns ordinary file exports into a single page. Because every tool draws on the same underlying figures, the numbers reconcile across the whole suite; the weekly one-page dashboard is the worked example carried through this catalogue.

## Operating principles

Every tool in this catalogue is built to the same rules:

1. **Simplicity over complexity.** Anything that doesn't earn its place on the dashboard gets stopped — the same rule the plan applies to everything else.
2. **Scripts over AI.** Deterministic code wherever the output is numbers or structure. AI is used only where the output is prose — and then only to produce drafts that a person approves. AI never touches figures and never publishes anything.
3. **Files in, one page out.** Every tool reads ordinary CSV exports from the existing systems. No live integrations in year one: nothing breaks if the group changes platforms, and nothing needs IT sign-off to start.
4. **No new software costs.** Python standard library only — no licences, subscriptions, servers or hosting. Each tool runs on any ordinary computer.
5. **One folder per tool.** Each tool is a small folder: the script, a plain-English guide, sample input and a one-page site configuration. Adopting a tool at another Elysian–Audley site means copying the folder and editing the configuration — nothing more.
6. **Same input, same output.** Tools are deterministic, so figures can always be re-checked and trusted.

## Tier 1 — Deterministic scripts (no AI anywhere)

| # | Tool | Reads → Produces | Used by | Value | Plan phase | Est. effort |
|---|------|------------------|---------|-------|------------|-------------|
| 1 | **Weekly one-page dashboard** | Cubigo sales, OpenTable bookings, Square settlements, flash-survey exports → one printed page | Manager + GM | Every review meeting starts from the same trusted page; no re-keying | Days 15–30 ("dashboard v1 live") | 2–3 days |
| 2 | Daily sales flash | Cubigo export → yesterday vs same weekday last week, top/bottom sellers | Manager + head chef | Good and bad days spotted while they can still be acted on | Days 15–30 | 1 day |
| 3 | Cubigo↔Square reconciliation | Both exports → card-settlement coverage report (out-of-band days, coverage gaps, fee-integrity exceptions) | Manager | Settlement anomalies caught early without false alarms on normal account billing | Days 15–30 | 1 day |
| 4 | Menu-engineering matrix | Cubigo product mix + Apicbase costings → popularity/margin quadrants | Manager + head chef | Menu decisions made on margin, not hunch | Days 31–60 | 2 days |
| 5 | Demand forecast for rotas | Bookings + covers history → next-week covers by daypart | Manager | Rotas matched to demand; the lever on labour % | Days 31–60 | 2 days |
| 6 | Allergen matrix sheet | Apicbase export → printable staff lookup | All FOH + kitchen | Compliance answers in seconds, always current | Days 31–60 | 1 day |
| 7 | Daily briefing sheet | Today's bookings + specials + allergen alerts + training rota → one printed page | All FOH | The daily 10-minute briefing prepared automatically | Days 31–60 | 1–2 days |
| 8 | Sunday pilot gate tracker | The same weekly exports → green/amber/red panel against the pilot's pre-agreed gates | Manager + GM | The week-8 stop/scale decision read off a panel, not argued about | Days 61–90 | 1 day |
| 9 | Waste log summariser | Daily waste entries → weekly cost-of-waste summary | Manager + kitchen | Waste made visible and costed every week | Days 31–60 | 1 day |

**Notes on selected tools:**

- **1 — Weekly dashboard.** The centrepiece: covers and revenue by daypart, resident vs external share against the agreed cap, spend per head, labour percentage, review counts and the plan's leading indicators — one page, produced the same way every Monday morning. Figures the systems cannot yet provide (for example resident dining frequency) are shown as "not yet tracked", never estimated. The page also discloses its own data quality: any unreadable rows or missing days are listed in the footer.
- **3 — Reconciliation.** Reconciles *card-settlement coverage*, not literal till-to-bank equality: because residents largely bill to their account, Square settles only a share of total till takings, so the tool flags days where that share falls outside an agreed band, days missing a settlement either way, and any Square row where gross minus fees doesn't equal net. The quiet check that surfaces a genuine void, refund or keying error without crying wolf over normal account billing.
- **5 — Demand forecast.** Deliberately a weighted moving average by day-of-week and daypart, with manual flags for bank holidays and events — not machine learning. With under a year of history, a transparent average a manager can interrogate beats a model nobody can.
- **8 — Gate tracker.** The Sunday lunch pilot's success gates (covers, spend, labour, satisfaction, repeat bookings) evaluated automatically each week from the same exports — so the stop/scale decision at week 8 is read off a panel, not argued about.

## Tier 2 — AI-assisted drafting (prose only; never numbers; always human-approved)

AI appears in exactly four places, all low-stakes drafting where a person reviews and approves every word before it goes anywhere:

1. **Review-response drafts** — reads new reviews (copied from each platform); produces draft replies in the house voice; used by the manager, who edits and posts. *Value:* every review answered promptly without formulaic copy. *Phase:* days 15–30, alongside the review-invitation programme. *Est. effort:* 1 day.
2. **Menu description and specials copy** — reads the dish list and weekly specials; produces draft wording for print and listings; used by the manager with the head chef. *Value:* consistent, appetising copy with no agency cost. *Phase:* days 31–60, with menu engineering round 1. *Est. effort:* half a day.
3. **Resident newsletter F&B section** — reads the feedback log and events calendar; produces a draft "You said / We did" section; used by the manager, approved by the GM before the newsletter goes out. *Value:* the feedback loop closed visibly every month. *Phase:* days 31–60. *Est. effort:* 1 day.
4. **Feedback theming** — reads free-text flash-survey comments; produces *suggested theme labels only* — a person approves the theme list, and counts per theme are then produced deterministically by keyword matching; used by the manager at the weekly review. *Value:* hundreds of comments turned into a short, trackable list. *Phase:* months 4–6, and only if plain keyword counting — which is tried first — proves insufficient. *Est. effort:* 1 day.

## Tier 3 — Deliberately not building in year one

Knowing what not to build is half the discipline:

- **Live system integrations** — wait for the directors' decision on the systems estate and IT sign-off; file exports work today.
- **Resident-facing chatbots** — wrong tone for a residents' home; high risk, no demand.
- **Dynamic pricing** — corrosive to resident trust; the plan grows spend through menu engineering instead.
- **Automated social posting** — two to three posts a week is a human job; automation adds brand risk and saves minutes.
- **Review-platform scraping** — against platform terms; manual exports and the invitation programme suffice.
- **Machine-learning forecasting** — revisit only after twelve months of clean history, and only if the simple average demonstrably underperforms.

## Exporting across the group

Anything that proves its value at Benjamin's travels: each tool is documented, configured per site through a single settings file, and reads file exports rather than talking to any one platform — so it works regardless of which POS or back-office systems a given village runs, today or after any estate change. A tool proven at one site can be adopted at thirty, at the cost of copying a folder.
