"""Validation experiments: metric calculation, success criteria, recommendations and CSV imports.

Metrics with different denominators are kept separate and every metric states its formula.
Revenue/purchases come from imported orders when present (they are more reliable than aggregate
counts); otherwise from recorded results. They are never added together, to avoid double counting.
"""
import csv
import hashlib
import io
import math
from datetime import date

from .. import db
from ..ingest.store import parse_date, pick

METRIC_DEFS = {
    "ctr": ("Click-through rate", "clicks ÷ impressions", "pct"),
    "landing_to_checkout": ("Landing → checkout rate", "checkout visits ÷ landing-page visits", "pct"),
    "purchase_conversion": ("Visitor → purchase rate", "purchases ÷ landing-page visits", "pct"),
    "checkout_conversion": ("Checkout → purchase rate", "purchases ÷ checkout visits", "pct"),
    "refund_rate": ("Refund rate", "refunds ÷ purchases", "pct"),
    "purchases": ("Purchases", "count", "int"),
    "gross_revenue": ("Gross revenue", "sum of sale amounts", "usd"),
    "refund_amount": ("Refunds", "sum of refunded amounts", "usd"),
    "net_sales": ("Net sales", "gross revenue − refunds", "usd"),
    "payment_fees": ("Payment fees", "recorded fees, or price × fee % + fixed fee per purchase", "usd"),
    "other_costs": ("Other variable costs", "sum of recorded costs (ads, tools, fulfillment)", "usd"),
    "contribution_margin": ("Contribution", "net sales − payment fees − other costs", "usd"),
    "contribution_margin_pct": ("Contribution margin", "contribution ÷ net sales", "pct"),
    "revenue_per_visitor": ("Net revenue per visitor", "net sales ÷ landing-page visits", "usd"),
    "rpm": ("Net revenue per 1,000 impressions", "net sales ÷ impressions × 1,000", "usd"),
}
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b}


def _sum(events, k):
    vals = [e[k] for e in events if e.get(k) is not None]
    return (sum(vals), True) if vals else (0, False)


def wilson(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, centre - half) * 100, 2), round(min(1, centre + half) * 100, 2)]


def compute(exp: dict, events: list[dict], orders: list[dict]) -> dict:
    t = {k: _sum(events, k) for k in ("impressions", "clicks", "landing_visits", "checkout_visits", "purchases",
                                       "gross_revenue", "refunds", "refund_amount", "payment_fees", "other_costs")}
    notes = []
    if orders:
        purchases = len(orders)
        gross = sum(o["amount"] for o in orders)
        refunds = sum(1 for o in orders if o["refunded_amount"] > 0)
        refund_amt = sum(o["refunded_amount"] for o in orders)
        fees_known = [o["fee"] for o in orders if o.get("fee") is not None]
        notes.append(f"Purchases and revenue come from {purchases} imported orders; funnel counts from recorded results.")
        if t["purchases"][1] and t["purchases"][0] != purchases:
            notes.append(f"Recorded results list {t['purchases'][0]} purchases vs {purchases} orders — orders were used.")
    else:
        purchases, gross = t["purchases"][0], t["gross_revenue"][0]
        refunds, refund_amt = t["refunds"][0], t["refund_amount"][0]
        fees_known = [t["payment_fees"][0]] if t["payment_fees"][1] else []
    have_purch = bool(orders) or t["purchases"][1]
    if fees_known and (not orders or len(fees_known) == len(orders)):
        fees, fees_est = sum(fees_known), False
    else:
        fees = gross * (exp.get("payment_fee_pct") or 0) / 100 + purchases * (exp.get("payment_fee_fixed") or 0)
        fees_est = True
        if purchases:
            notes.append("Payment fees are estimated from the experiment's fee settings (no fee data imported).")
    net = gross - refund_amt
    costs = t["other_costs"][0]
    contribution = net - fees - costs
    imp, clk, lv, cv = (t[k][0] for k in ("impressions", "clicks", "landing_visits", "checkout_visits"))
    has = {k: t[k][1] for k in t}

    def ratio(n, d, ok=True):
        return round(100 * n / d, 2) if ok and d else None

    vals = {
        "ctr": ratio(clk, imp, has["impressions"] and has["clicks"]),
        "landing_to_checkout": ratio(cv, lv, has["landing_visits"] and has["checkout_visits"]),
        "purchase_conversion": ratio(purchases, lv, has["landing_visits"] and have_purch),
        "checkout_conversion": ratio(purchases, cv, has["checkout_visits"] and have_purch),
        "refund_rate": ratio(refunds, purchases, have_purch),
        "purchases": purchases if have_purch else None,
        "gross_revenue": round(gross, 2) if have_purch else None,
        "refund_amount": round(refund_amt, 2) if have_purch else None,
        "net_sales": round(net, 2) if have_purch else None,
        "payment_fees": round(fees, 2) if have_purch else None,
        "other_costs": round(costs, 2) if has["other_costs"] else None,
        "contribution_margin": round(contribution, 2) if have_purch else None,
        "contribution_margin_pct": ratio(contribution, net, have_purch and net > 0),
        "revenue_per_visitor": round(net / lv, 2) if have_purch and has["landing_visits"] and lv else None,
        "rpm": round(net / imp * 1000, 2) if have_purch and has["impressions"] and imp else None,
    }
    metrics = [{"key": k, "label": METRIC_DEFS[k][0], "formula": METRIC_DEFS[k][1], "unit": METRIC_DEFS[k][2],
                "value": v, "estimated": (k == "payment_fees" and fees_est and v is not None)} for k, v in vals.items()]
    totals = {"impressions": imp if has["impressions"] else None, "clicks": clk if has["clicks"] else None,
              "landing_visits": lv if has["landing_visits"] else None,
              "checkout_visits": cv if has["checkout_visits"] else None}
    ci = wilson(purchases, lv) if has["landing_visits"] and have_purch and lv else None
    return {"values": vals, "metrics": metrics, "totals": totals, "notes": notes, "purchase_conversion_ci95": ci,
            "has_data": bool(events or orders)}


def evaluate(exp: dict, m: dict) -> dict:
    vals = m["values"]
    results = []
    for cr in exp.get("criteria") or []:
        v = vals.get(cr.get("metric"))
        op = OPS.get(cr.get("op", ">="))
        try:
            th = float(cr.get("value"))
        except (TypeError, ValueError):
            th = None
        met = None if v is None or op is None or th is None else bool(op(v, th))
        md = METRIC_DEFS.get(cr.get("metric"), (cr.get("metric"), "", "num"))
        results.append({**cr, "label": md[0], "unit": md[2], "observed": v, "met": met, "no_threshold": th is None})
    lv = m["totals"]["landing_visits"] or 0
    target = exp.get("target_exposure") or 0
    ended = bool(exp.get("end_date")) and exp["end_date"] <= date.today().isoformat()
    if not m["has_data"]:
        rec, why = "pending", "No results recorded yet."
    elif not results:
        rec, why = "define", "Add success criteria to get a recommendation."
    elif any(r["no_threshold"] for r in results):
        # Live run: auto-created criteria had no thresholds, and the old message blamed "missing data".
        rec, why = "define", "Set a threshold for each success criterion (Experiment design) to get a recommendation."
    elif target and lv < target and not ended:
        rec, why = "continue", f"{lv:,} of {target:,} target visitors reached — keep the test running before deciding."
    elif any(r["met"] is None for r in results):
        rec, why = "continue", "Some criteria can't be evaluated yet because required data is missing."
    elif all(r["met"] for r in results):
        rec, why = "go", "All predefined success criteria were met."
    elif not any(r["met"] for r in results):
        rec, why = "stop", "None of the predefined success criteria were met."
    else:
        rec, why = "revise", "Some criteria were met and some were not — revise the offer, price or channel and retest."
    if target and lv < target and rec in ("go", "stop", "revise"):
        why += f" Note: only {lv:,} of {target:,} target visitors — the sample is smaller than planned."
    if (m["values"].get("contribution_margin") or 0) < 0 and rec == "go":
        why += " Warning: contribution is negative."
    return {"criteria": results, "recommendation": rec, "reason": why}


# ---------- CSV imports ----------

EVENT_COLS = {
    "date": ("date", "day", "period", "week"),
    "impressions": ("impressions", "views", "reach", "sends", "delivered", "recipients"),
    "clicks": ("clicks", "link_clicks", "unique_clicks"),
    "landing_visits": ("landing_visits", "visits", "sessions", "visitors", "page_views", "pageviews", "unique_visitors"),
    "checkout_visits": ("checkout_visits", "checkouts", "checkout_starts", "initiated_checkout", "add_to_cart"),
    "purchases": ("purchases", "orders", "sales", "conversions"),
    "gross_revenue": ("gross_revenue", "revenue", "gross", "sales_amount", "amount"),
    "refunds": ("refunds", "refund_count"),
    "refund_amount": ("refund_amount", "refunded", "refunded_amount"),
    "payment_fees": ("payment_fees", "fees", "fee"),
    "other_costs": ("other_costs", "costs", "cost", "ad_spend", "spend"),
}
ORDER_ID = ("order_id", "id", "sale_id", "charge_id", "transaction_id", "order", "order_number", "payment_id")
ORDER_AMT = ("amount", "total", "price", "gross", "sale_price", "amount_paid")
ORDER_REF = ("amount_refunded", "refunded_amount", "refund_amount", "refunded")
ORDER_FEE = ("fee", "fees", "processing_fee", "stripe_fee")
ORDER_DATE = ("created_(utc)", "created", "date", "created_at", "purchase_date", "sale_date")


def _num(v):
    if v in (None, ""):
        return None
    s = str(v).replace("$", "").replace(",", "").strip()
    if s.lower() in ("true", "yes"):
        return None
    try:
        n = float(s)
        return n if n >= 0 else None
    except ValueError:
        return None


def parse_csv(text: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for r in csv.DictReader(io.StringIO(text), dialect=dialect):
        rows.append({str(k).strip().lower().replace(" ", "_"): (v.strip() if isinstance(v, str) else v)
                     for k, v in r.items() if k is not None})
    return rows


def import_csv(experiment_id: str, text: str) -> dict:
    rows = parse_csv(text)
    if not rows:
        return {"kind": None, "imported": 0, "skipped": 0, "errors": ["The CSV file has no rows."]}
    keys = set(rows[0])
    is_orders = bool(keys & set(ORDER_ID)) and bool(keys & set(ORDER_AMT)) and not (keys & {"impressions", "visits", "sessions", "landing_visits"})
    imported = skipped = 0
    errors = []
    with db.tx() as c:
        for i, r in enumerate(rows, 2):
            if is_orders:
                oid, amt = pick(r, ORDER_ID), _num(pick(r, ORDER_AMT))
                if not oid or amt is None:
                    errors.append(f"Row {i}: missing order ID or amount")
                    continue
                refunded = pick(r, ORDER_REF)
                ref_amt = _num(refunded)
                if ref_amt is None and str(refunded).lower() in ("true", "yes", "1"):
                    ref_amt = amt
                cur = c.execute("INSERT OR IGNORE INTO orders (id, experiment_id, order_ref, date, amount, refunded_amount, fee, origin, created_at) "
                                "VALUES (?,?,?,?,?,?,?,?,?)",
                                (db.new_id("ord"), experiment_id, str(oid), parse_date(pick(r, ORDER_DATE)), amt,
                                 ref_amt or 0, _num(pick(r, ORDER_FEE)), "csv", db.now()))
                imported += cur.rowcount
                skipped += 1 - cur.rowcount
            else:
                rec = {}
                for field, aliases in EVENT_COLS.items():
                    v = pick(r, aliases)
                    if field == "date":
                        rec[field] = parse_date(v)
                    else:
                        n = _num(v)
                        rec[field] = (int(n) if n is not None and field in ("impressions", "clicks", "landing_visits",
                                                                            "checkout_visits", "purchases", "refunds") else n)
                if all(rec[k] is None for k in rec if k != "date"):
                    errors.append(f"Row {i}: no recognizable numbers")
                    continue
                key = hashlib.sha256(repr(sorted(r.items())).encode()).hexdigest()[:24]
                cur = c.execute(
                    "INSERT OR IGNORE INTO experiment_events (id, experiment_id, date, impressions, clicks, landing_visits, "
                    "checkout_visits, purchases, gross_revenue, refunds, refund_amount, payment_fees, other_costs, origin, "
                    "import_key, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (db.new_id("ee"), experiment_id, rec["date"], rec["impressions"], rec["clicks"], rec["landing_visits"],
                     rec["checkout_visits"], rec["purchases"], rec["gross_revenue"], rec["refunds"], rec["refund_amount"],
                     rec["payment_fees"], rec["other_costs"], "csv", key, db.now()))
                imported += cur.rowcount
                skipped += 1 - cur.rowcount
        exp = c.execute("SELECT audience_id, name FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        db.log_activity(c, exp[0], "experiment", f"Imported {imported} {'orders' if is_orders else 'result rows'} into '{exp[1]}'")
    return {"kind": "orders" if is_orders else "results", "imported": imported, "skipped_duplicates": skipped,
            "errors": errors[:20]}
