"""Creator-facing outputs built from a statement: the payout file (bank / Wise batch), a fingerprinted PDF
statement, and a read-only creator portal page (one self-contained HTML file, no scripts) to send the creator.

Nothing here moves money or publishes anything: files are written to data/exports for a human to send.
"""
import csv
import hashlib
import html
import json
import re
from datetime import date

from .. import config, db
from . import agency, optimize


def _e(s) -> str:
    return html.escape("" if s is None else str(s))


def _m(v) -> str:
    return "—" if v is None else f"${v:,.2f}"


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "creator").strip("_")[:60] or "creator"


def fingerprint(st: dict) -> str:
    """SHA-256 over the numbers a creator relies on. Re-generating an unchanged statement gives the same value,
    so the creator (or you) can tell whether a later copy differs."""
    core = {"creator": st["organization"]["id"], "period": st["period"], "deal": {
                k: (st["deal"] or {}).get(k) for k in ("id", "creator_share_pct", "basis", "loss_carry_forward",
                                                       "min_guarantee_monthly", "guarantee_months")},
            "lines": [{k: l.get(k) for k in ("product_id", "orders", "gross", "refunds", "fees", "shared_costs",
                                             "split_base", "creator_share")} for l in st["lines"]],
            "entitlement": st["all_time_creator_share"], "paid_out": st["paid_out"], "balance_owed": st["balance_owed"]}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


# ---------- payout file ----------

PAYOUT_COLS = ["name", "recipientEmail", "paymentReference", "receiverType", "amountCurrency", "amount",
               "sourceCurrency", "targetCurrency"]


def payout_rows(include_demo: bool = False) -> list[dict]:
    """One row per creator with a positive balance owed. Columns follow Wise's batch-payment CSV
    (email recipients); any bank can read the same columns."""
    rows = []
    for o in db.all_("SELECT * FROM organizations ORDER BY name"):
        if o["is_demo"] and not include_demo:
            continue
        st = agency.statement(o["id"])
        bal = st["balance_owed"]
        if not bal or bal <= 0:
            continue
        rows.append({"organization_id": o["id"], "creator": o["name"],
                     "name": o.get("contact_name") or o["name"], "recipientEmail": o.get("contact_email") or "",
                     "paymentReference": f"Rev share {date.today():%Y-%m}", "receiverType": "PRIVATE",
                     "amountCurrency": "target", "amount": f"{bal:.2f}", "sourceCurrency": "USD", "targetCurrency": "USD",
                     "missing_email": not o.get("contact_email")})
    return rows


def payout_csv(include_demo: bool = False):
    rows = payout_rows(include_demo)
    path = config.EXPORTS_DIR / f"payouts_{date.today():%Y-%m-%d}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(PAYOUT_COLS)
        for r in rows:
            w.writerow([r[c] for c in PAYOUT_COLS])
    return path, rows


# ---------- PDF statement ----------

def statement_pdf(st: dict):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    org, d, t = st["organization"], st["deal"], st["totals"]
    path = config.EXPORTS_DIR / f"statement_{_slug(org['name'])}_{date.today():%Y-%m-%d}.pdf"
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8.5, leading=11)
    story = [Paragraph(f"Revenue-share statement — {_e(org['name'])}", ss["Title"]),
             Paragraph(f"Period: {_e(st['period']['start'] or 'all time')} to {_e(st['period']['end'] or 'today')} · "
                       f"Prepared {date.today():%B %d, %Y}", small), Spacer(1, 8)]
    if d:
        terms = (f"Creator {d['creator_share_pct']:g}% / agency {100 - d['creator_share_pct']:g}% of "
                 f"{'contribution (net sales − payment fees − shared costs)' if d['basis'] == 'contribution' else 'net sales after payment fees'}.")
        terms += " Losses carry forward." if d.get("loss_carry_forward") else " Losses are not charged to the creator."
        if d.get("min_guarantee_monthly"):
            terms += (f" Minimum guarantee ${d['min_guarantee_monthly']:,.2f}/month (recoupable"
                      + (f", {d['guarantee_months']} months" if d.get("guarantee_months") else "") + ").")
        story.append(Paragraph(_e(terms), small))
    else:
        story.append(Paragraph("No active deal — creator share can't be computed.", small))
    story.append(Spacer(1, 10))
    head = ["Product", "Orders", "Net sales", "Fees", "Shared costs", "Split base", "Creator share"]
    data = [head] + [[Paragraph(_e(l["product"]), small), l["orders"], _m(l["net_sales"]), _m(l["fees"]),
                      _m(l["shared_costs"]), _m(l["split_base"]), _m(l["creator_share"])] for l in st["lines"]]
    data.append(["Total", t["orders"], _m(t["net_sales"]), _m(t["fees"]), _m(t["shared_costs"]), _m(t["split_base"]),
                 _m(t["creator_share"]) if d else "—"])
    tbl = Table(data, colWidths=[2.0 * inch] + [0.85 * inch] * 6, repeatRows=1)
    tbl.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                             ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
                             ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [tbl, Spacer(1, 12)]
    en = st.get("entitlement") or {}
    bal_rows = [["Earned share (all time)", _m(en.get("earned"))]]
    if en.get("guarantee_top_up"):
        bal_rows.append([f"Minimum-guarantee top-up ({en['guarantee_months_completed']} months)", _m(en["guarantee_top_up"])])
    if en.get("loss_carried_forward"):
        bal_rows.append(["Loss carried forward (offsets future profit)", _m(en["loss_carried_forward"])])
    bal_rows += [["Entitlement to date", _m(st["all_time_creator_share"])], ["Paid out", _m(st["paid_out"])],
                 ["Balance owed to creator", _m(st["balance_owed"])]]
    bt = Table(bal_rows, colWidths=[3.6 * inch, 1.3 * inch])
    bt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)]))
    story += [bt, Spacer(1, 10)]
    for w in st["warnings"]:
        story.append(Paragraph("Note: " + _e(w), small))
    if st["payouts"]:
        story += [Spacer(1, 8), Paragraph("Payouts", ss["Heading3"])]
        story += [Paragraph(f"{_e(p['date'])} — {_m(p['amount'])} {_e(p.get('reference') or '')}", small) for p in st["payouts"]]
    story += [Spacer(1, 18), Paragraph("Approved by (agency): ______________________   Date: __________", small),
              Spacer(1, 10), Paragraph("Acknowledged by (creator): ___________________   Date: __________", small),
              Spacer(1, 14), Paragraph(f"Statement fingerprint (SHA-256): {fingerprint(st)}", small),
              Paragraph("An unchanged statement always gives the same fingerprint. Payments are made outside "
                        "AudienceOS; it does not move money.", small)]
    SimpleDocTemplate(str(path), pagesize=letter, title=f"Statement — {org['name']}",
                      leftMargin=0.7 * inch, rightMargin=0.7 * inch).build(story)
    return path


# ---------- read-only creator portal ----------

PORTAL_CSS = """
:root{--bg:#fff;--fg:#111827;--mute:#6b7280;--line:#e5e7eb;--card:#f9fafb;--accent:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#0b0f17;--fg:#e5e7eb;--mute:#9ca3af;--line:#1f2937;--card:#111827;--accent:#60a5fa}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:40px 24px 64px}h1{font-size:28px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.sub{color:var(--mute);font-size:13px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:24px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}.stat b{display:block;font-size:22px}
.stat span{color:var(--mute);font-size:12px}table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mute);font-weight:500}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}tr.tot td{font-weight:600;border-top:2px solid var(--fg)}
.note{background:var(--card);border-left:3px solid var(--accent);padding:10px 14px;border-radius:6px;font-size:13px;margin:8px 0}
.foot{margin-top:40px;color:var(--mute);font-size:12px}code{font-size:11px;word-break:break-all}
@media (max-width:700px){.stats{grid-template-columns:1fr 1fr}}
"""


def portal_html(st: dict) -> str:
    org, d, t = st["organization"], st["deal"], st["totals"]
    products = db.all_("SELECT p.* FROM products p JOIN audiences a ON a.id=p.audience_id WHERE a.organization_id=? "
                       "AND p.status IN ('launched','paused','retired') ORDER BY p.launched_at", (org["id"],))
    for p in products:
        p["pnl"] = agency.product_pnl(p)
    rows = optimize.compare_products(products)
    terms = "No active deal yet."
    if d:
        terms = (f"You receive {d['creator_share_pct']:g}% of "
                 f"{'contribution (net sales minus payment fees and shared costs)' if d['basis'] == 'contribution' else 'net sales after payment fees'}."
                 + (" Losses carry forward and are offset against later profits." if d.get("loss_carry_forward")
                    else " Losses are never charged to you."))
        if d.get("min_guarantee_monthly"):
            terms += f" Minimum guarantee: {_m(d['min_guarantee_monthly'])} per month (recoupable against your share)."
    lines = "".join(f"<tr><td>{_e(l['product'])}</td><td class=n>{l['orders']}</td><td class=n>{_m(l['net_sales'])}</td>"
                    f"<td class=n>{_m(l['fees'])}</td><td class=n>{_m(l['shared_costs'])}</td><td class=n>{_m(l['split_base'])}</td>"
                    f"<td class=n>{_m(l['creator_share'])}</td></tr>" for l in st["lines"])
    lines += (f"<tr class=tot><td>Total</td><td class=n>{t['orders']}</td><td class=n>{_m(t['net_sales'])}</td>"
              f"<td class=n>{_m(t['fees'])}</td><td class=n>{_m(t['shared_costs'])}</td><td class=n>{_m(t['split_base'])}</td>"
              f"<td class=n>{_m(t['creator_share']) if d else '—'}</td></tr>")
    prod = "".join(f"<tr><td>{_e(r['product'])}</td><td class=n>{_m(r['price'])}</td><td class=n>{r['orders']}</td>"
                   f"<td class=n>{_m(r['net_sales'])}</td><td>{_e(r['best_channel'] or '—')}</td>"
                   f"<td class=n>{'—' if r['refund_rate_pct'] is None else str(r['refund_rate_pct']) + '%'}</td></tr>" for r in rows)
    chan: dict[str, dict] = {}
    for p in products:
        for k, v in p["pnl"]["by_channel"].items():
            c = chan.setdefault(k, {"orders": 0, "net_sales": 0.0})
            c["orders"] += v["orders"]
            c["net_sales"] += v["net_sales"]
    chans = "".join(f"<tr><td>{_e(k)}</td><td class=n>{v['orders']}</td><td class=n>{_m(v['net_sales'])}</td></tr>"
                    for k, v in sorted(chan.items(), key=lambda kv: -kv[1]["net_sales"]))
    pays = "".join(f"<tr><td>{_e(p['date'])}</td><td class=n>{_m(p['amount'])}</td><td>{_e(p.get('reference') or '')}</td></tr>"
                   for p in st["payouts"]) or "<tr><td colspan=3 class=sub>No payouts yet.</td></tr>"
    en = st.get("entitlement") or {}
    extra = ""
    if en.get("guarantee_top_up"):
        extra += f"<div class=note>Includes a minimum-guarantee top-up of {_m(en['guarantee_top_up'])} ({en['guarantee_months_completed']} months).</div>"
    if en.get("loss_carried_forward"):
        extra += f"<div class=note>A loss of {_m(en['loss_carried_forward'])} is carried forward and will be offset against future profit.</div>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{_e(org['name'])} — Earnings</title><style>{PORTAL_CSS}</style></head><body><main>
<h1>{_e(org['name'])}</h1><div class=sub>Earnings and products · updated {date.today():%B %d, %Y} · read-only</div>
<div class=stats><div class=stat><span>Net sales</span><b>{_m(t['net_sales'])}</b><span>{t['orders']} orders</span></div>
<div class=stat><span>Your earnings to date</span><b>{_m(st['all_time_creator_share'])}</b><span>all time</span></div>
<div class=stat><span>Paid to you</span><b>{_m(st['paid_out'])}</b><span>{len(st['payouts'])} payouts</span></div>
<div class=stat><span>Balance owed to you</span><b>{_m(st['balance_owed'])}</b><span>next payout</span></div></div>
<p class=sub style="margin-top:14px">{_e(terms)}</p>{extra}
<h2>Statement</h2><table><thead><tr><th>Product</th><th class=n>Orders</th><th class=n>Net sales</th><th class=n>Fees</th>
<th class=n>Shared costs</th><th class=n>Split base</th><th class=n>Your share</th></tr></thead><tbody>{lines}</tbody></table>
<h2>Products</h2><table><thead><tr><th>Product</th><th class=n>Price</th><th class=n>Orders</th><th class=n>Net sales</th>
<th>Best channel</th><th class=n>Refund rate</th></tr></thead><tbody>{prod or '<tr><td colspan=6 class=sub>No launched products yet.</td></tr>'}</tbody></table>
<h2>Where buyers came from</h2><table><thead><tr><th>Channel</th><th class=n>Orders</th><th class=n>Net sales</th></tr></thead>
<tbody>{chans or '<tr><td colspan=3 class=sub>No sales yet.</td></tr>'}</tbody></table>
<h2>Payouts</h2><table><thead><tr><th>Date</th><th class=n>Amount</th><th>Reference</th></tr></thead><tbody>{pays}</tbody></table>
<div class=foot>{''.join(f'<div>{_e(w)}</div>' for w in st['warnings'])}
<p>Net sales = sales minus refunds. Split base = net sales minus payment fees{' minus shared costs' if d and d['basis'] == 'contribution' else ''}.
Payments are made outside this page.</p><p>Statement fingerprint: <code>{fingerprint(st)}</code></p></div>
</main></body></html>"""


def write_portal(st: dict):
    path = config.EXPORTS_DIR / f"portal_{_slug(st['organization']['name'])}.html"
    path.write_text(portal_html(st))
    return path
