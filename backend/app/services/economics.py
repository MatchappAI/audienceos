"""Revenue scenarios from explicitly stated assumptions. Formulas are returned alongside results.
No conversion benchmarks are built in: purchase rates are user inputs labeled as such."""
import math


def scenario(price: float | None, fulfillment: float | None, production: float | None, a: dict) -> dict:
    P = float(price or 0)
    F = float(fulfillment or 0)
    K = float(production or 0)
    f = float(a.get("payment_fee_pct") or 0) / 100
    ff = float(a.get("payment_fee_fixed") or 0)
    fee = P * f + ff
    uc = P - F - fee
    out = {
        "inputs": {"price": P, "fulfillment_cost_per_unit": F, "production_cost": K, "payment_fee_pct": f * 100,
                   "payment_fee_fixed": ff, "reach": a.get("reach"), "exposure_pct": a.get("exposure_pct"),
                   "rates_pct": a.get("rates_pct") or []},
        "unit_contribution": round(uc, 2),
        "fee_per_sale": round(fee, 2),
        "breakeven_units": math.ceil(K / uc) if uc > 0 and K > 0 else (0 if uc > 0 else None),
        "formulas": [
            "Payment fee per sale = price × fee % + fixed fee",
            "Contribution per sale = price − fulfillment cost − payment fee",
            "Break-even sales = production cost ÷ contribution per sale",
            "Buyers = reach × exposure % × purchase rate %",
            "Net contribution = buyers × contribution per sale − production cost",
        ],
        "rows": [],
        "warnings": [],
    }
    if uc <= 0:
        out["warnings"].append("Each sale loses money at this price and cost — the economics don't work as stated.")
    R, e = a.get("reach"), a.get("exposure_pct")
    if not R or e in (None, ""):
        out["warnings"].append("Enter audience reach and the share you expect to see the offer to model scenarios.")
        return out
    exposed = float(R) * float(e) / 100
    for r in a.get("rates_pct") or []:
        buyers = exposed * float(r) / 100
        out["rows"].append({"rate_pct": r, "exposed": round(exposed), "buyers": round(buyers, 1),
                            "gross_revenue": round(buyers * P, 2), "net_contribution": round(buyers * uc - K, 2)})
    return out
