"""Agency economics: product P&L, creator revenue-share statements, payouts, and the per-creator pipeline stage.

Definitions (shown in the UI next to every number):
  Net sales           = gross sales − refunds
  Split base (net_sales basis)    = net sales − payment fees
  Split base (contribution basis) = net sales − payment fees − shared costs
  Creator share       = max(0, split base) × creator %     (losses are not charged to the creator)
  Agency share        = split base − creator share
  Balance owed        = all-time creator share − all-time payouts
"""
from decimal import ROUND_HALF_UP, Decimal

from .. import db


def money(x: float) -> float:
    """Round to cents, half-up (what people expect on a statement)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

STAGES = ["discovery", "analysis", "opportunities", "validation", "product", "launched", "selling"]
STAGE_LABEL = {"discovery": "Discovery", "analysis": "Audience analysis", "opportunities": "Product opportunities",
               "validation": "Demand validation", "product": "Product ready for approval", "launched": "Launched",
               "selling": "Selling & optimizing"}


def _in(d, start, end):
    return (not start or (d or "") >= start) and (not end or (d or "9999") <= end)


def product_pnl(product: dict, start: str | None = None, end: str | None = None) -> dict:
    sales = [s for s in db.all_("SELECT * FROM product_sales WHERE product_id=?", (product["id"],)) if _in(s["date"], start, end)]
    costs = [c for c in db.all_("SELECT * FROM product_costs WHERE product_id=?", (product["id"],)) if _in(c["date"], start, end)]
    gross = sum(s["amount"] for s in sales)
    refunds = sum(s["refunded_amount"] for s in sales)
    fees_missing = sum(1 for s in sales if s["fee"] is None)
    fees = sum(s["fee"] or 0 for s in sales)
    shared = sum(c["amount"] for c in costs if c["shared"])
    unshared = sum(c["amount"] for c in costs if not c["shared"])
    net = gross - refunds
    by_channel: dict[str, dict] = {}
    for s in sales:
        k = s["channel"] or "unattributed"
        b = by_channel.setdefault(k, {"orders": 0, "net_sales": 0.0})
        b["orders"] += 1
        b["net_sales"] = round(b["net_sales"] + s["amount"] - s["refunded_amount"], 2)
    return {"orders": len(sales), "refunded_orders": sum(1 for s in sales if s["refunded_amount"] > 0),
            "gross": round(gross, 2), "refunds": round(refunds, 2), "net_sales": round(net, 2), "fees": round(fees, 2),
            "fees_missing": fees_missing, "shared_costs": round(shared, 2), "agency_only_costs": round(unshared, 2),
            "contribution": round(net - fees - shared - unshared, 2),
            "margin_pct": round(100 * (net - fees - shared - unshared) / net, 1) if net > 0 else None,
            "by_channel": by_channel}


def active_deal(org_id: str) -> dict | None:
    return db.one("SELECT * FROM deals WHERE organization_id=? AND status='active' ORDER BY created_at DESC LIMIT 1", (org_id,))


def statement(org_id: str, start: str | None = None, end: str | None = None) -> dict:
    org = db.one("SELECT * FROM organizations WHERE id=?", (org_id,))
    deal = active_deal(org_id)
    products = db.all_("SELECT p.* FROM products p JOIN audiences a ON a.id=p.audience_id WHERE a.organization_id=? "
                       "ORDER BY p.created_at", (org_id,))
    pct = deal["creator_share_pct"] if deal else None
    basis = deal["basis"] if deal else None
    lines, tot = [], {k: 0.0 for k in ("gross", "refunds", "net_sales", "fees", "shared_costs", "agency_only_costs",
                                       "split_base", "creator_share", "agency_share", "orders")}
    for p in products:
        pnl = product_pnl(p, start, end)
        base = pnl["net_sales"] - pnl["fees"] - (pnl["shared_costs"] if basis == "contribution" else 0)
        cshare = money(max(0.0, base) * pct / 100) if pct is not None else None
        line = {"product_id": p["id"], "product": p["name"], "status": p["status"], "launched_at": p.get("launched_at"), **pnl, "split_base": round(base, 2),
                "creator_share": cshare, "agency_share": money(base - cshare) if cshare is not None else None}
        lines.append(line)
        for k in tot:
            tot[k] += line.get(k) or 0
    tot = {k: round(v, 2) for k, v in tot.items()}
    tot["agency_net_after_own_costs"] = round(tot["agency_share"] - tot["agency_only_costs"], 2)
    # Balance uses all-time figures regardless of the period filter.
    all_time = statement_totals_all_time(org_id, pct, basis) if pct is not None else None
    paid = db.scalar("SELECT COALESCE(SUM(amount),0) FROM payouts WHERE organization_id=?", (org_id,)) or 0
    warnings = []
    if not deal:
        warnings.append("No active deal — set the revenue-share terms before reporting creator obligations.")
    if any(l["fees_missing"] for l in lines):
        warnings.append("Some sales have no payment-fee data; fees are counted as $0 for those orders. Import fee columns from your checkout export.")
    if any(l["split_base"] < 0 for l in lines):
        warnings.append("At least one product has a negative split base. Losses are not charged to the creator.")
    return {"organization": org, "deal": deal, "period": {"start": start, "end": end}, "lines": lines, "totals": tot,
            "payouts": db.all_("SELECT * FROM payouts WHERE organization_id=? ORDER BY date DESC", (org_id,)),
            "all_time_creator_share": all_time, "paid_out": round(paid, 2),
            "balance_owed": round(all_time - paid, 2) if all_time is not None else None, "warnings": warnings,
            "definitions": __doc__.split("Definitions (shown in the UI next to every number):")[1].strip()}


def statement_totals_all_time(org_id, pct, basis) -> float:
    total = 0.0
    for p in db.all_("SELECT p.* FROM products p JOIN audiences a ON a.id=p.audience_id WHERE a.organization_id=?", (org_id,)):
        pnl = product_pnl(p)
        base = pnl["net_sales"] - pnl["fees"] - (pnl["shared_costs"] if basis == "contribution" else 0)
        total += money(max(0.0, base) * pct / 100)
    return round(total, 2)


def stage(org_id: str) -> str:
    q = lambda sql: db.scalar(sql, (org_id,))
    aud = "(SELECT id FROM audiences WHERE organization_id=?)"
    if q(f"SELECT COUNT(*) FROM product_sales ps JOIN products p ON p.id=ps.product_id WHERE p.audience_id IN {aud}"):
        return "selling"
    if q(f"SELECT COUNT(*) FROM products WHERE status='launched' AND audience_id IN {aud}"):
        return "launched"
    if q(f"SELECT COUNT(*) FROM products WHERE audience_id IN {aud}"):
        return "product"
    if q(f"SELECT COUNT(*) FROM experiments WHERE audience_id IN {aud}"):
        return "validation"
    if q(f"SELECT COUNT(*) FROM opportunities WHERE status!='rejected' AND audience_id IN {aud}"):
        return "opportunities"
    if q(f"SELECT COUNT(*) FROM sources WHERE audience_id IN {aud}"):
        return "analysis"
    return "discovery"


LAUNCH_CHECKLIST = [
    ("creator_approved", "The creator has reviewed and approved the product and every public claim"),
    ("claims_checked", "All marketing assets for this product are approved (no unresolved claim flags)"),
    ("checkout_tested", "A test purchase and refund went through the external checkout"),
    ("delivery_tested", "The buyer receives the product (download/access/email) after purchase"),
    ("support_ready", "Refund policy and support contact are published on the sales page"),
]
