"""Agency economics: product P&L, creator revenue-share statements, payouts, and the per-creator pipeline stage.

Definitions (shown in the UI next to every number):
  Net sales           = gross sales − refunds
  Split base (net_sales basis)    = net sales − payment fees
  Split base (contribution basis) = net sales − payment fees − shared costs
  Creator share       = max(0, split base) × creator %     (losses are not charged to the creator)
  Agency share        = split base − creator share
  Loss carry-forward (deal option, off by default):
                        losses on any product, in any period, offset profits before the creator's share is
                        taken — creator share = max(0, cumulative split base of all products) × creator %
  Minimum guarantee (deal option): a recoupable monthly minimum for each COMPLETED month since the deal
                        start (capped at the guaranteed months) — entitlement = max(earned share, guarantee to date)
  Balance owed        = all-time entitlement − all-time payouts
"""
from datetime import date
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
        cf = bool(deal and deal.get("loss_carry_forward"))
        cshare = (money((base if cf else max(0.0, base)) * pct / 100)) if pct is not None else None
        line = {"product_id": p["id"], "product": p["name"], "status": p["status"], "launched_at": p.get("launched_at"), **pnl, "split_base": round(base, 2),
                "creator_share": cshare, "agency_share": money(base - cshare) if cshare is not None else None}
        lines.append(line)
        for k in tot:
            tot[k] += line.get(k) or 0
    tot = {k: round(v, 2) for k, v in tot.items()}
    tot["orders"] = int(tot["orders"])
    if deal and deal.get("loss_carry_forward") and pct is not None:  # losses offset profits across products
        tot["creator_share"] = money(max(0.0, tot["split_base"]) * pct / 100)
        tot["agency_share"] = money(tot["split_base"] - tot["creator_share"])
    tot["agency_net_after_own_costs"] = round(tot["agency_share"] - tot["agency_only_costs"], 2)
    # Balance uses all-time figures regardless of the period filter.
    entitlement = entitlement_all_time(org_id, deal) if deal else None
    all_time = entitlement["entitlement"] if entitlement else None
    paid = db.scalar("SELECT COALESCE(SUM(amount),0) FROM payouts WHERE organization_id=?", (org_id,)) or 0
    warnings = []
    if not deal:
        warnings.append("No active deal — set the revenue-share terms before reporting creator obligations.")
    if any(l["fees_missing"] for l in lines):
        warnings.append("Some sales have no payment-fee data; fees are counted as $0 for those orders. Import fee columns from your checkout export.")
    if any(l["split_base"] < 0 for l in lines):
        warnings.append("At least one product has a negative split base. "
                        + ("Under this deal's loss carry-forward, it offsets profits on other products and later periods."
                           if deal and deal.get("loss_carry_forward") else "Losses are not charged to the creator."))
    return {"organization": org, "deal": deal, "period": {"start": start, "end": end}, "lines": lines, "totals": tot,
            "payouts": db.all_("SELECT * FROM payouts WHERE organization_id=? ORDER BY date DESC", (org_id,)),
            "all_time_creator_share": all_time, "entitlement": entitlement, "paid_out": round(paid, 2),
            "balance_owed": round(all_time - paid, 2) if all_time is not None else None, "warnings": warnings,
            "definitions": __doc__.split("Definitions (shown in the UI next to every number):")[1].strip()}


def statement_totals_all_time(org_id, pct, basis, carry_forward: bool = False) -> float:
    """Earned creator share, all time. Per-product floor at 0 unless losses carry forward deal-wide."""
    total, cum = 0.0, 0.0
    for p in db.all_("SELECT p.* FROM products p JOIN audiences a ON a.id=p.audience_id WHERE a.organization_id=?", (org_id,)):
        pnl = product_pnl(p)
        base = pnl["net_sales"] - pnl["fees"] - (pnl["shared_costs"] if basis == "contribution" else 0)
        cum += base
        total += money(max(0.0, base) * pct / 100)
    return money(max(0.0, cum) * pct / 100) if carry_forward else round(total, 2)


def cumulative_split_base(org_id, basis) -> float:
    cum = 0.0
    for p in db.all_("SELECT p.* FROM products p JOIN audiences a ON a.id=p.audience_id WHERE a.organization_id=?", (org_id,)):
        pnl = product_pnl(p)
        cum += pnl["net_sales"] - pnl["fees"] - (pnl["shared_costs"] if basis == "contribution" else 0)
    return round(cum, 2)


def completed_months(start: str, until: date) -> int:
    """Whole calendar months completed from `start` (YYYY-MM-DD) up to `until`."""
    try:
        s = date.fromisoformat(start[:10])
    except (TypeError, ValueError):
        return 0
    m = (until.year - s.year) * 12 + (until.month - s.month) - (1 if until.day < s.day else 0)
    return max(0, m)


def entitlement_all_time(org_id: str, deal: dict, today: date | None = None) -> dict:
    """What the creator is entitled to so far: earned share, plus any minimum-guarantee top-up."""
    pct, basis, cf = deal["creator_share_pct"], deal["basis"], bool(deal.get("loss_carry_forward"))
    earned = statement_totals_all_time(org_id, pct, basis, cf)
    cum = cumulative_split_base(org_id, basis)
    out = {"earned": earned, "loss_carry_forward": cf,
           "loss_carried_forward": round(-cum, 2) if cf and cum < 0 else 0.0,
           "guarantee_monthly": deal.get("min_guarantee_monthly"), "guarantee_months_completed": 0,
           "guaranteed_to_date": 0.0, "guarantee_top_up": 0.0}
    g = deal.get("min_guarantee_monthly")
    if g:
        today = today or date.today()
        until = today
        if deal.get("end_date"):
            try:
                until = min(today, date.fromisoformat(deal["end_date"][:10]))
            except ValueError:
                pass
        months = completed_months(deal.get("start_date") or deal["created_at"][:10], until)
        if deal.get("guarantee_months"):
            months = min(months, int(deal["guarantee_months"]))
        out["guarantee_months_completed"] = months
        out["guaranteed_to_date"] = money(g * months)
        out["guarantee_top_up"] = money(max(0.0, out["guaranteed_to_date"] - earned))
    out["entitlement"] = money(earned + out["guarantee_top_up"])
    return out


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
