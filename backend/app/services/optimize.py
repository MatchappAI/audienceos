"""Optimization loop: look at a launched product's sales, channels, refunds, margin and past experiments, and
suggest the next test. Rules only (no model) — every suggestion states the numbers it is based on, and a human
decides whether to run it. Suggestions are ordered by how much they can move results for the least effort.
"""
from datetime import date

from .. import db

MIN_ORDERS_FOR_CHANNEL_CALL = 5     # below this, channel shares are noise
UNATTRIBUTED_LIMIT = 0.30           # share of orders without a channel before tracking is the first fix
REFUND_LIMIT = 0.10                 # refund rate that needs investigating
LOW_MARGIN_PCT = 30.0
QUIET_DAYS = 14                     # launched this long with no orders → change the offer


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None


def _prefill(p: dict, name: str, hypothesis: str, price=None, channel=None) -> dict:
    return {"audience_id": p["audience_id"], "opportunity_id": p.get("opportunity_id"), "name": name,
            "hypothesis": hypothesis, "price": p.get("price") if price is None else price, "channel": channel,
            "offer": p["name"], "checkout_url": p.get("checkout_url")}


def tested_prices(p: dict) -> list[float]:
    prices = {p["price"]} if p.get("price") is not None else set()
    prices |= {x["price"] for x in db.all_(
        "SELECT price FROM experiments WHERE price IS NOT NULL AND (opportunity_id=? OR (audience_id=? AND offer=?))",
        (p.get("opportunity_id"), p["audience_id"], p["name"]))}
    return sorted(prices)


def suggestions(p: dict) -> list[dict]:
    """`p` is a product dict with `pnl` (agency.product_pnl)."""
    if p["status"] not in ("launched", "paused") and not p["pnl"]["orders"]:
        return []
    pnl, out = p["pnl"], []
    orders = pnl["orders"]
    chans = {k: v for k, v in pnl["by_channel"].items()}
    unattributed = chans.get("unattributed", {}).get("orders", 0)

    # 1. Tracking first: without channels nothing else can be compared.
    if orders and unattributed / orders > UNATTRIBUTED_LIMIT:
        out.append({"kind": "tracking", "effort": "low",
                    "title": "Add a tracking link to every place the product is promoted",
                    "why": f"{unattributed} of {orders} orders ({round(100 * unattributed / orders)}%) have no channel, so "
                           "channels can't be compared. Add ?utm_source=<channel> (or client_reference_id for Stripe "
                           "Payment Links) to each link."})

    # 2. No sales after launch → the offer, not the channel, is the problem.
    quiet = _days_since(p.get("launched_at"))
    if p["status"] == "launched" and orders == 0 and quiet is not None and quiet >= QUIET_DAYS:
        lower = round(p["price"] * 0.7, 2) if p.get("price") else None
        out.append({"kind": "offer", "effort": "medium",
                    "title": "Rework the offer: new angle or lower entry price",
                    "why": f"Launched {quiet} days ago with no orders. Test the strongest audience quote as the headline"
                           + (f", and a ${lower:g} entry price (−30%)." if lower else "."),
                    "experiment": _prefill(p, f"Offer test: {p['name']}", "A headline built on the audience's own words "
                                           "converts better than the current page.", price=lower)})

    # 3. Price test when only one price has ever been tried.
    prices = tested_prices(p)
    if p.get("price") and orders >= MIN_ORDERS_FOR_CHANNEL_CALL and len(prices) <= 1:
        refund_rate = pnl["refunded_orders"] / orders if orders else 0
        up = refund_rate < REFUND_LIMIT
        new_price = round(p["price"] * (1.25 if up else 0.8), 2)
        out.append({"kind": "price", "effort": "low",
                    "title": f"Price test: ${new_price:g} vs ${p['price']:g}",
                    "why": f"Only ${p['price']:g} has been tested, across {orders} orders. "
                           + ("Refunds are low, so test higher (+25%)." if up else
                              f"Refunds are {round(100 * refund_rate)}%, so test lower (−20%) before anything else."),
                    "experiment": _prefill(p, f"Price test ${new_price:g}: {p['name']}",
                                           f"Buyers will pay ${new_price:g} at a conversion rate that raises net sales per visitor.",
                                           price=new_price)})

    # 4. Double down on the best channel; test a second one.
    named = {k: v for k, v in chans.items() if k != "unattributed"}
    attributed = sum(v["orders"] for v in named.values())
    if attributed >= MIN_ORDERS_FOR_CHANNEL_CALL:
        best, b = max(named.items(), key=lambda kv: kv[1]["net_sales"])
        share = b["orders"] / attributed
        if len(named) == 1:
            out.append({"kind": "channel", "effort": "medium",
                        "title": f"Test a second channel alongside {best}",
                        "why": f"All {attributed} attributed orders came from {best}. One more channel shows whether "
                               "demand exists beyond it (newsletter, a pinned post, or a collaborator).",
                        "experiment": _prefill(p, f"Channel test: {p['name']}", f"A channel other than {best} produces "
                                               "orders at a similar conversion rate.")})
        elif share >= 0.6:
            out.append({"kind": "channel", "effort": "low",
                        "title": f"Put more promotion into {best}",
                        "why": f"{best} brought {b['orders']} of {attributed} attributed orders ({round(100 * share)}%) "
                               f"and ${b['net_sales']:,.2f} net sales. Schedule two more placements there and compare.",
                        "experiment": _prefill(p, f"More {best}: {p['name']}", f"Two more {best} placements add orders at "
                                               "the same rate as the first.", channel=best)})

    # 5. Refunds.
    if orders >= MIN_ORDERS_FOR_CHANNEL_CALL and pnl["refunded_orders"] / orders >= REFUND_LIMIT:
        out.append({"kind": "refunds", "effort": "medium",
                    "title": "Find out why buyers ask for refunds",
                    "why": f"{pnl['refunded_orders']} of {orders} orders were refunded "
                           f"({round(100 * pnl['refunded_orders'] / orders)}%, ${pnl['refunds']:,.2f}). Email refunded "
                           "buyers one question, and check that the sales page matches what's delivered."})

    # 6. Margin.
    if pnl["margin_pct"] is not None and pnl["margin_pct"] < LOW_MARGIN_PCT and orders:
        out.append({"kind": "margin", "effort": "medium",
                    "title": "Cut the biggest cost before scaling",
                    "why": f"Margin is {pnl['margin_pct']:g}% after fees and costs (${pnl['contribution']:,.2f} "
                           f"contribution on ${pnl['net_sales']:,.2f} net sales). More sales at this margin mostly "
                           "grow costs."})

    # 7. A completed experiment says "revise" but nothing new was tried.
    if p.get("opportunity_id"):
        xs = db.all_("SELECT * FROM experiments WHERE opportunity_id=? ORDER BY created_at DESC", (p["opportunity_id"],))
        if xs and xs[0].get("decision") == "revise" and xs[0]["status"] == "completed":
            out.append({"kind": "revise", "effort": "medium",
                        "title": f"Run the revision you decided on for '{xs[0]['name']}'",
                        "why": f"The last experiment was marked 'revise'"
                               + (f": {xs[0]['decision_note']}" if xs[0].get("decision_note") else "") + ", and no newer "
                               "experiment exists.",
                        "experiment": _prefill(p, f"Revision: {p['name']}", xs[0].get("next_action") or xs[0].get("hypothesis") or "")})
    return out


def compare_products(products: list[dict]) -> list[dict]:
    """Launched products side by side: net sales per order, margin, best channel."""
    rows = []
    for p in products:
        pnl = p["pnl"]
        named = {k: v for k, v in pnl["by_channel"].items() if k != "unattributed"}
        best = max(named.items(), key=lambda kv: kv[1]["net_sales"])[0] if named else None
        rows.append({"product_id": p["id"], "product": p["name"], "price": p.get("price"), "orders": pnl["orders"],
                     "net_sales": pnl["net_sales"], "net_per_order": round(pnl["net_sales"] / pnl["orders"], 2) if pnl["orders"] else None,
                     "margin_pct": pnl["margin_pct"], "best_channel": best,
                     "refund_rate_pct": round(100 * pnl["refunded_orders"] / pnl["orders"], 1) if pnl["orders"] else None})
    return sorted(rows, key=lambda r: -r["net_sales"])


