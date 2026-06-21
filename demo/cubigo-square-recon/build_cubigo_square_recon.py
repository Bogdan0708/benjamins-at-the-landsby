import csv
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
import benjamins_common as bc

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
CUBIGO_COLS = ["date", "time", "check_id", "item", "category", "covers", "net", "guest_type"]
SQUARE_COLS = ["date", "gross", "fees", "net"]

NOTE = ("This reconciles card-settlement coverage, not total takings. "
        "Resident account billing means Square is expected to be lower than "
        "Cubigo total till.")


def _validate_cubigo(fn, row):
    bc.parse_date(row["date"])  # unparseable date -> data-quality skip, not a trading day
    try:
        float(row["net"])  # non-numeric/empty net -> skip+count this row
    except (ValueError, TypeError):
        raise bc.BenjaminsError(f"unreadable net {row['net']!r}")


def _validate_square(fn, row):
    bc.parse_date(row["date"])  # unparseable date -> data-quality skip, not a phantom settlement
    for col in ("gross", "fees", "net"):
        try:
            float(row[col])
        except (ValueError, TypeError):
            raise bc.BenjaminsError(f"unreadable {col} {row[col]!r}")


def compute(cubigo_path, square_path, config):
    """Card-settlement coverage reconciliation.

    For each trading date we compare the Cubigo total till net against the
    Square card-settlement row. Residents largely bill to a monthly account,
    so card settlement (Square gross) is *expected* to sit below the till
    total — the coverage ratio band, not equality, is the invariant.

    A day is an exception if it trips any of three independent checks:
      1. coverage ratio (square_gross / till_net) outside [ratio_low, ratio_high]
      2. coverage gap (a date in one system but not the other)
      3. square fee integrity (abs(gross - fees - net) > fee_tolerance)
    """
    ratio_low, ratio_high = config["ratio_band"]
    fee_tol = config["fee_tolerance"]

    cubigo_rows, skipped = bc.read_csv_rows(cubigo_path, CUBIGO_COLS, _validate_cubigo)
    square_rows, sq_skipped = bc.read_csv_rows(square_path, SQUARE_COLS, _validate_square)
    skipped = skipped + sq_skipped

    # till_net per day = sum of valid-float cubigo net for that date.
    till = defaultdict(float)
    till_seen = set()
    for r in cubigo_rows:
        till[r["date"]] += float(r["net"])
        till_seen.add(r["date"])

    # one Square row per settled date (gross, fees, net).
    square = {}
    for r in square_rows:
        square[r["date"]] = {
            "gross": round(float(r["gross"]), 2),
            "fees": round(float(r["fees"]), 2),
            "net": round(float(r["net"]), 2),
        }

    rows, exceptions = [], []
    for d in sorted(set(till_seen) | set(square)):
        in_cubigo = d in till_seen
        in_square = d in square
        till_net = round(till[d], 2) if in_cubigo else None
        sq = square[d] if in_square else None
        sq_gross = sq["gross"] if sq else None
        sq_fees = sq["fees"] if sq else None
        sq_net = sq["net"] if sq else None

        reasons = []

        # 1. coverage ratio band (only when both sides present and till_net != 0)
        ratio = None
        if in_cubigo and in_square and till_net:
            ratio = round(sq_gross / till_net, 4)
            if ratio < ratio_low or ratio > ratio_high:
                reasons.append(
                    f"coverage ratio {ratio:.4f} outside band "
                    f"[{ratio_low:.2f}, {ratio_high:.2f}]")

        # 2. coverage gap (one-sided date)
        if in_cubigo and not in_square:
            reasons.append("no card settlement for trading day")
        elif in_square and not in_cubigo:
            reasons.append("settlement with no till trading")

        # 3. square fee integrity (whenever a Square row exists)
        if in_square and abs(sq_gross - sq_fees - sq_net) > fee_tol:
            reasons.append(
                f"square fee integrity: gross-fees-net = "
                f"{round(sq_gross - sq_fees - sq_net, 2)}")

        row = {"date": d, "till_net": till_net, "sq_gross": sq_gross,
               "sq_fees": sq_fees, "sq_net": sq_net, "ratio": ratio,
               "reasons": reasons}
        rows.append(row)
        if reasons:
            exceptions.append(row)

    # summary over the days that HAVE a ratio.
    ratios = [r["ratio"] for r in rows if r["ratio"] is not None]
    if ratios:
        summary = {
            "compared": len(ratios),
            "mean_ratio": round(sum(ratios) / len(ratios), 4),
            "min_ratio": round(min(ratios), 4),
            "max_ratio": round(max(ratios), 4),
        }
    else:
        summary = {"compared": 0, "mean_ratio": None,
                   "min_ratio": None, "max_ratio": None}

    return {"rows": rows, "exceptions": exceptions, "summary": summary,
            "skipped": skipped}


def _reason_text(reasons):
    return "; ".join(reasons)


def render(metrics):
    cur = CONFIG["currency"]
    s = metrics["summary"]
    n_exc = len(metrics["exceptions"])
    esc = html.escape

    body = "<h2>Card-settlement coverage reconciliation</h2>"
    body += f'<p class="explain">{esc(NOTE)}</p>'

    def fmt_ratio(v):
        return f"{v:.4f}" if v is not None else "—"

    body += (f"<p>{s['compared']} day(s) compared. "
             f"Mean ratio {fmt_ratio(s['mean_ratio'])}, "
             f"min {fmt_ratio(s['min_ratio'])}, max {fmt_ratio(s['max_ratio'])}. "
             f"{n_exc} exception day(s).</p>")

    if metrics["exceptions"]:
        body += ("<table><tr><td><strong>Date</strong></td>"
                 "<td><strong>Till net</strong></td>"
                 "<td><strong>Square gross</strong></td>"
                 "<td><strong>Ratio</strong></td>"
                 "<td><strong>Reason</strong></td></tr>")
        for r in metrics["exceptions"]:
            body += (f"<tr><td>{esc(r['date'])}</td>"
                     f"<td>{bc.fmt_money(r['till_net'], cur)}</td>"
                     f"<td>{bc.fmt_money(r['sq_gross'], cur)}</td>"
                     f"<td>{fmt_ratio(r['ratio'])}</td>"
                     f"<td>{esc(_reason_text(r['reasons']))}</td></tr>")
        body += "</table>"
    else:
        body += "<p>No exception days — every trading day reconciled within the band.</p>"

    return bc.page("Cubigo–Square coverage reconciliation", CONFIG["site_name"],
                   body, metrics["skipped"], "card-settlement coverage")


def main():
    try:
        metrics = compute("sample-data/cubigo-sales.csv",
                          "sample-data/square-settlements.csv",
                          CONFIG)
    except bc.BenjaminsError as e:
        print(f"Could not build the reconciliation: {e}", file=sys.stderr)
        raise SystemExit(1)
    Path("cubigo-square-recon.html").write_text(render(metrics))
    with open("mismatches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "till_net", "sq_gross", "sq_net", "ratio", "reason"])
        for r in metrics["exceptions"]:
            w.writerow([
                r["date"],
                "" if r["till_net"] is None else r["till_net"],
                "" if r["sq_gross"] is None else r["sq_gross"],
                "" if r["sq_net"] is None else r["sq_net"],
                "" if r["ratio"] is None else r["ratio"],
                _reason_text(r["reasons"]),
            ])
    print("Wrote cubigo-square-recon.html and mismatches.csv")


if __name__ == "__main__":
    main()
