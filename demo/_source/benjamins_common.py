#!/usr/bin/env python3
"""Benjamin's at The Landsby — shared plumbing for the demo tools.

Generic, per-tool-agnostic helpers extracted from the weekly dashboard:
date parsing, CSV/JSON loading, formatting, an inline-SVG bar chart, and a
one-page HTML wrapper (shared head/CSS, synthetic-data watermark, and the
data-quality footer). No per-tool business rules live here — each tool passes
its own column set, row validator, and body markup in.

Python standard library only. Same input always produces the same output.

This module is vendored (copied byte-identically) into each tool folder.
"""
import csv
import html
import json
from datetime import datetime, timedelta
from pathlib import Path


class BenjaminsError(Exception):
    """A problem explained in plain English; callers print it without a traceback."""


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise BenjaminsError(f"unreadable date {s!r} (expected YYYY-MM-DD)")


def week_ending(d):
    """The Sunday on or after d (weeks end on Sunday)."""
    return d + timedelta(days=(6 - d.weekday()) % 7)


def daypart(time_str):
    try:
        h, m = (int(x) for x in time_str.split(":")[:2])
        mins = h * 60 + m
    except (ValueError, TypeError, AttributeError):
        raise BenjaminsError(f"unreadable time {time_str!r} (expected HH:MM)")
    if mins < 15 * 60:
        return "Lunch"
    if mins < 17 * 60 + 30:
        return "Afternoon"
    return "Evening"


def read_csv_rows(filename, expected_columns=None, validator=None):
    """Read a CSV, skipping & counting malformed rows.

    Returns (rows, skipped): valid rows as dicts, and human-readable skip
    descriptions. The per-tool column set and field checks are passed in:

      expected_columns  list[str] — every name must appear in the header,
                        else BenjaminsError (the export format changed).
      validator         callable(filename, row) — raise BenjaminsError to
                        skip+count that row instead of aborting.

    Truncated/over-wide rows (DictReader's None key or None values) are always
    skipped, since they would crash downstream code.
    """
    path = Path(filename)
    if not path.exists():
        raise BenjaminsError(
            f"Cannot find '{path.name}' at {path}.\n"
            f"Export it from the relevant system, save it in place, and run again."
        )
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            found = reader.fieldnames or []
            if expected_columns:
                missing = [c for c in expected_columns if c not in found]
                if missing:
                    raise BenjaminsError(
                        f"'{path.name}' does not look like the expected export — "
                        f"the export format may have changed.\n"
                        f"  Missing columns: {', '.join(missing)}\n"
                        f"  Found columns:   {', '.join(found)}"
                    )
            rows, skipped = [], []
            # accessing reader.fieldnames above forced the header read, so the
            # first data row is line 2 — hence enumerate starts at 2.
            for n, row in enumerate(reader, start=2):
                if None in row or None in row.values():
                    skipped.append(f"{path.name} line {n}: wrong number of fields")
                    continue
                if validator is not None:
                    try:
                        validator(path.name, row)
                    except BenjaminsError as e:
                        skipped.append(f"{path.name} line {n}: {e}")
                        continue
                rows.append(row)
            return rows, skipped
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        raise BenjaminsError(f"Cannot read '{path.name}': {e}")


def load_json_file(path, what):
    path = Path(path)
    if not path.exists():
        raise BenjaminsError(f"Cannot find '{path.name}' ({what}). Expected at: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BenjaminsError(f"'{path.name}' ({what}) is not valid JSON (line {e.lineno}): {e.msg}")
    except (OSError, UnicodeDecodeError) as e:
        raise BenjaminsError(f"Cannot read '{path.name}' ({what}): {e}")


def fmt_money(v, cur):
    return f"{cur}{v:,.0f}" if v is not None else "—"


def fmt_pct(v):
    return f"{v:.0%}" if v is not None else "—"


def fmt_score(v):
    return f"{v:.1f}" if v is not None else "—"


def fmt_day(d):
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


def bar_chart(pairs, width=460, height=140, prefix=""):
    """Inline SVG bar chart from (label, value) pairs. No dependencies."""
    if not pairs:
        return "<p>No data.</p>"
    max_v = max(v for _, v in pairs) or 1
    bar_w = width // len(pairs)
    # 18px headroom above y=0: the tallest bar's value label sits at y = -5.
    parts = [f'<svg viewBox="0 -18 {width} {height + 54}" class="chart" role="img">']
    for i, (label, value) in enumerate(pairs):
        h = round(value / max_v * height)
        x = i * bar_w
        parts.append(
            f'<rect x="{x + 6}" y="{height - h}" width="{bar_w - 12}" height="{h}" rx="2"/>'
            f'<text x="{x + bar_w // 2}" y="{height + 16}" text-anchor="middle" class="lbl">{html.escape(str(label))}</text>'
            f'<text x="{x + bar_w // 2}" y="{height - h - 5}" text-anchor="middle" class="val">{prefix}{value:,.0f}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def page(title, site_name, body_html, skipped, generated_label, watermark=True):
    """Wrap a one-pager: shared head/CSS, synthetic-data watermark, body, and
    the data-quality footer (lists skipped rows and any missing days).

    title            short page title (e.g. "weekly dashboard")
    site_name        the venue/site name shown in the header
    body_html        the tool-specific page body (already-built HTML)
    skipped          list[str] of skipped-row / missing-day descriptions
    generated_label  what this page covers (e.g. "week ending 7 June 2026")
    watermark        show the "synthetic, for demonstration" banner
    """
    esc = html.escape

    if skipped:
        items = "".join(f"<li>{esc(s)}</li>" for s in skipped)
        footer_html = (
            f'<div class="note">{len(skipped)} data-quality note(s):<ul>{items}</ul></div>'
        )
    else:
        footer_html = '<div class="note">All rows read; no data-quality issues detected.</div>'

    watermark_html = (
        '<div class="watermark">SAMPLE DATA — synthetic, for demonstration</div>'
        if watermark else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<title>{esc(site_name)} — {esc(title)}</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #222; margin: 24px auto; max-width: 960px; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline;
            border-bottom: 3px double #1f3a2d; padding-bottom: 8px; }}
  h1 {{ font-size: 22px; margin: 0; color: #1f3a2d; }}
  .watermark {{ background: #fff3cd; border: 1px solid #b8860b; color: #7a5800;
                padding: 3px 10px; font: 12px sans-serif; border-radius: 3px; }}
  .week {{ font: 13px sans-serif; color: #555; }}
  .kpis {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin: 16px 0; }}
  .kpi {{ border: 1px solid #ccc; border-radius: 4px; padding: 8px; }}
  .kpi-label {{ font: 11px sans-serif; color: #555; text-transform: uppercase; }}
  .kpi-value {{ font-size: 19px; margin-top: 4px; }}
  .sub {{ font: 11px sans-serif; color: #777; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  h2 {{ font-size: 14px; color: #1f3a2d; border-bottom: 1px solid #ddd; padding-bottom: 3px; }}
  .chart rect {{ fill: #1f3a2d; }}
  .chart .lbl, .chart .val {{ font: 10px sans-serif; fill: #444; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  td {{ padding: 3px 6px; border-bottom: 1px solid #eee; }}
  td:last-child {{ text-align: right; }}
  ul {{ margin: 4px 0 4px 18px; padding: 0; font-size: 12px; }}
  footer {{ margin-top: 18px; border-top: 1px solid #ccc; font: 12px sans-serif; color: #555; }}
  .note {{ margin-top: 6px; }}
  @media print {{ body {{ margin: 0; }} @page {{ size: A4; margin: 12mm; }} }}
</style>
</head>
<body>
<header>
  <div>
    <h1>{esc(site_name)} — {esc(title)}</h1>
    <div class="week">{esc(generated_label)}</div>
  </div>
  {watermark_html}
</header>
{body_html}
<footer><strong>Data quality</strong>{footer_html}</footer>
</body>
</html>"""
