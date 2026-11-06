"""Research report export: HTML (self-contained), PDF, JSON and CSV. Built only from stored data."""
import csv
import html
import json
import re

from .. import config, db
from . import economics, experiments, intel, scoring

INTENT_LABEL = {"engagement": "Engagement", "curiosity": "Curiosity", "free_info_request": "Free-info request",
                "existing_spending": "Existing spending", "buying_question": "Buying question",
                "paid_solution_request": "Asks to buy", "verified_purchase": "Purchase"}


def gather(audience_id: str) -> dict:
    a = db.one("SELECT a.*, o.name AS org_name, o.kind AS org_kind, o.is_demo AS org_demo FROM audiences a "
               "JOIN organizations o ON o.id=a.organization_id WHERE a.id=?", (audience_id,))
    data = {"generated_at": db.now(), "audience": a,
            "channels": db.all_("SELECT * FROM channels WHERE audience_id=?", (audience_id,)),
            "sources": db.all_("SELECT id, kind, platform, voice, title, original_url, filename, status, retrieval_method, "
                               "retrieved_at, obtained_json, missing_json FROM sources WHERE audience_id=? ORDER BY created_at",
                               (audience_id,)),
            "intelligence": intel.intelligence(audience_id)}
    an = data["intelligence"]["analysis"]
    opps = db.all_("SELECT * FROM opportunities WHERE audience_id=? AND status != 'rejected' AND analysis_id IS ? "
                   "ORDER BY total_score DESC", (audience_id, an["id"] if an else None)) if an else []
    for o in opps:
        o["evidence"] = db.all_("SELECT e.id, e.quote, e.locator, s.title AS source_title, s.platform FROM evidence e "
                                "JOIN opportunity_evidence oe ON oe.evidence_id=e.id LEFT JOIN sources s ON s.id=e.source_id "
                                "WHERE oe.opportunity_id=?", (o["id"],))
        o["scenario_result"] = economics.scenario(o["price"], o["fulfillment_cost_per_unit"], o["production_cost"],
                                                  o.get("scenario") or {})
        o["score_breakdown"] = scoring.explain(o.get("scores") or {})
    data["opportunities"] = opps
    data["competitors"] = db.all_("SELECT * FROM competitors WHERE audience_id=?", (audience_id,))
    exps = db.all_("SELECT * FROM experiments WHERE audience_id=?", (audience_id,))
    for x in exps:
        ev = db.all_("SELECT * FROM experiment_events WHERE experiment_id=?", (x["id"],))
        od = db.all_("SELECT * FROM orders WHERE experiment_id=?", (x["id"],))
        m = experiments.compute(x, ev, od)
        x["metrics"], x["evaluation"] = m, experiments.evaluate(x, m)
    data["experiments"] = exps
    return data


def _e(s):
    return html.escape(str(s if s is not None else ""))


def _money(v):
    return "—" if v is None else f"${v:,.2f}"


def render_html(d: dict) -> str:
    a, it = d["audience"], d["intelligence"]
    an, prof = it["analysis"], (it["analysis"] or {}).get("profile") or {}
    demo = '<div class="demo">DEMONSTRATION DATA — synthetic, not a real audience</div>' if a.get("is_demo") else ""
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{_e(a['name'])} — AudienceOS report</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{{font:15px/1.6 -apple-system,BlinkMacSystemFont,system-ui,sans-serif;color:#1d1d1f;max-width:900px;margin:0 auto;padding:40px 28px}}
h1{{font-size:32px;margin:0}}h2{{font-size:21px;margin:40px 0 10px;border-bottom:1px solid #e5e5ea;padding-bottom:6px}}
h3{{font-size:16px;margin:24px 0 6px}}.muted{{color:#6e6e73}}table{{border-collapse:collapse;width:100%;margin:8px 0}}
td,th{{text-align:left;border-bottom:1px solid #eee;padding:6px 8px;vertical-align:top;font-size:14px}}th{{color:#6e6e73;font-weight:600}}
blockquote{{margin:6px 0;padding:4px 12px;border-left:3px solid #d2d2d7;color:#333}}.tag{{display:inline-block;font-size:12px;
padding:1px 8px;border-radius:99px;background:#f2f2f7;margin-right:4px}}.demo{{background:#fff4ce;padding:8px 12px;border-radius:8px;
font-weight:600;margin-bottom:16px}}.note{{background:#f5f5f7;padding:10px 14px;border-radius:8px}}
</style></head><body>{demo}<h1>{_e(a['name'])}</h1><p class="muted">{_e(a['org_name'])} · Report generated {_e(d['generated_at'][:16].replace('T', ' '))} UTC</p>"""]
    if an:
        parts.append(f"<p class='note'>Analysis of {_e(an['stats'].get('units'))} units of material "
                     f"({_e(an['stats'].get('comments_analyzed'))} comments, {_e(an['stats'].get('content_items'))} content items) "
                     f"by <b>{_e(an['provider'])} {_e(an.get('model') or '')}</b>"
                     f"{' — external provider' if an.get('external') else ' — processed on this Mac'}. "
                     f"Scores are relative attractiveness for testing, not probabilities. Prices and economics are hypotheses.</p>")
    else:
        parts.append("<p class='note'>No completed analysis yet.</p>")
    if prof:
        parts.append(f"<h2>Audience overview</h2><p>{_e(prof.get('summary'))}</p><p><b>Intended audience:</b> {_e(prof.get('intended_audience'))}</p>")
        parts.append("<p>" + "".join(f"<span class='tag'>{_e(t['name'])}</span>" for t in prof.get("topics", [])) + "</p>")
        if prof.get("audience_characteristics"):
            parts.append("<h3>Audience characteristics</h3><ul>" + "".join(
                f"<li>{_e(c['claim'])} <span class='muted'>— {'supported by ' + str(len(c.get('evidence', []))) + ' source excerpt(s)' if c.get('supported') else 'no linked evidence (treat as unverified)'}</span></li>"
                for c in prof["audience_characteristics"]) + "</ul>")
    if it["clusters"]:
        parts.append("<h2>Recurring problems</h2><table><tr><th>Problem</th><th>Voices</th><th>Sources</th><th>Intent (0–5)</th><th>Evidence</th></tr>")
        for c in it["clusters"]:
            parts.append(f"<tr><td><b>{_e(c['label'])}</b><br><span class='muted'>{_e(c['description'])}</span></td>"
                         f"<td>{c['unique_authors']}</td><td>{c['source_count']}</td><td>{c['intent_score']}</td><td>{_e(c['evidence_quality'])}</td></tr>")
        parts.append("</table>")
        for c in it["clusters"][:8]:
            parts.append(f"<h3>{_e(c['label'])}</h3>" + "".join(
                f"<blockquote>“{_e(q['quote'])}”<br><span class='muted'>{INTENT_LABEL[q['intent_level']]} · {_e(q['platform'])} · {_e(q['source_title'] or '')}{(' · ' + _e(q['locator'])) if q['locator'] else ''}</span></blockquote>"
                for q in c["quotes"][:4]))
    if it["purchasing"]:
        parts.append("<h2>Purchasing signals</h2>" + "".join(
            f"<blockquote>“{_e(q['quote'])}”<br><span class='muted'>{INTENT_LABEL[q['intent_level']]} · {_e(q['source_title'] or '')}</span></blockquote>"
            for q in it["purchasing"][:15]))
    if prof.get("market_gaps"):
        parts.append("<h2>Market gaps (model interpretation)</h2><ul>" + "".join(f"<li>{_e(g['gap'])}</li>" for g in prof["market_gaps"]) + "</ul>")
    if d["opportunities"]:
        parts.append("<h2>Product opportunities</h2>")
        for o in d["opportunities"]:
            sr = o["scenario_result"]
            conf = o.get("confidence") or {}
            parts.append(f"""<h3>{_e(o['name'])} <span class='tag'>{_e(o['product_type'])}</span> <span class='tag'>Index {o['total_score']}/100</span></h3>
<table><tr><th>Buyer</th><td>{_e(o['buyer'])}</td></tr><tr><th>Problem</th><td>{_e(o['problem'])}</td></tr>
<tr><th>Test price</th><td>{_money(o['price'])} {_e(o['price_model'])} — {_e(o['price_rationale'])}</td></tr>
<tr><th>Format</th><td>{_e(o['format_rationale'])}</td></tr><tr><th>Production</th><td>{_e(o['production'])}</td></tr>
<tr><th>Economics (assumptions)</th><td>Production {_money(o['production_cost'])}, fulfillment {_money(o['fulfillment_cost_per_unit'])}/sale,
contribution {_money(sr['unit_contribution'])}/sale, break-even {sr['breakeven_units'] if sr['breakeven_units'] is not None else 'n/a'} sales</td></tr>
<tr><th>Alternatives</th><td>{_e(o['competition_notes'])} <span class='muted'>(model's general knowledge — unverified)</span></td></tr>
<tr><th>Distribution</th><td>{_e(o['distribution'])}</td></tr><tr><th>Validation test</th><td>{_e(o['validation_plan'])}</td></tr>
<tr><th>Risks</th><td>{'<br>'.join(_e(r) for r in o.get('risks') or [])}</td></tr>
<tr><th>Supported</th><td>{'<br>'.join(_e(r) for r in conf.get('supported') or [])}</td></tr>
<tr><th>Assumed</th><td>{'<br>'.join(_e(r) for r in conf.get('assumed') or [])}</td></tr>
<tr><th>Missing evidence</th><td>{'<br>'.join(_e(r) for r in o.get('missing_evidence') or [])}</td></tr></table>"""
                         + "".join(f"<blockquote>“{_e(e['quote'])}”<br><span class='muted'>{_e(e['source_title'] or '')}</span></blockquote>" for e in o["evidence"][:4]))
    if d["experiments"]:
        parts.append("<h2>Validation experiments</h2>")
        for x in d["experiments"]:
            v = x["metrics"]["values"]
            parts.append(f"<h3>{_e(x['name'])}</h3><p>Recommendation: <b>{_e(x['evaluation']['recommendation'])}</b> — {_e(x['evaluation']['reason'])}"
                         f"{' · Your decision: <b>' + _e(x['decision']) + '</b>' if x.get('decision') else ''}</p><table>"
                         + "".join(f"<tr><th>{_e(m['label'])}</th><td>{'—' if m['value'] is None else (str(m['value']) + '%' if m['unit'] == 'pct' else (_money(m['value']) if m['unit'] == 'usd' else m['value']))}</td><td class='muted'>{_e(m['formula'])}</td></tr>"
                                   for m in x["metrics"]["metrics"]) + "</table>")
    if an and an.get("unknowns"):
        parts.append("<h2>Important unknowns</h2><ul>" + "".join(f"<li>{_e(u)}</li>" for u in an["unknowns"]) + "</ul>")
    parts.append("<h2>Sources</h2><table><tr><th>Source</th><th>Status</th><th>Obtained</th><th>Missing</th></tr>" + "".join(
        f"<tr><td>{_e(s['title'] or s['original_url'] or s['filename'])}<br><span class='muted'>{_e(s['platform'])} · {_e(s['retrieval_method'] or '')} · {_e((s['retrieved_at'] or '')[:10])}</span></td>"
        f"<td>{_e(s['status'])}</td><td>{'<br>'.join(_e(x) for x in s['obtained'])}</td><td>{'<br>'.join(_e(x) for x in s['missing'])}</td></tr>"
        for s in d["sources"]) + "</table></body></html>")
    return "".join(parts)


def render_pdf(d: dict, path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    ss = getSampleStyleSheet()
    P = lambda t, s="BodyText": Paragraph(_e(t), ss[s])
    a, it = d["audience"], d["intelligence"]
    an = it["analysis"]
    prof = (an or {}).get("profile") or {}
    story = []
    if a.get("is_demo"):
        story.append(P("DEMONSTRATION DATA — synthetic, not a real audience", "Heading4"))
    story += [P(a["name"], "Title"), P(f"{a['org_name']} · generated {d['generated_at'][:16]} UTC"), Spacer(1, 8)]
    if an:
        story.append(P(f"Analyzed by {an['provider']} {an.get('model') or ''}. Scores are relative attractiveness for testing, "
                       "not probabilities. Prices and economics are hypotheses."))
    if prof:
        story += [P("Audience overview", "Heading2"), P(prof.get("summary", ""))]
    if it["clusters"]:
        story.append(P("Recurring problems", "Heading2"))
        for c in it["clusters"][:10]:
            story.append(P(f"{c['label']} — {c['unique_authors']} voices, {c['source_count']} sources, intent {c['intent_score']}/5, "
                           f"evidence: {c['evidence_quality']}", "Heading4"))
            for q in c["quotes"][:3]:
                story.append(P(f"“{q['quote'][:300]}” ({INTENT_LABEL[q['intent_level']]}, {q['source_title'] or q['platform']})"))
    if d["opportunities"]:
        story.append(P("Product opportunities", "Heading2"))
        for o in d["opportunities"]:
            sr = o["scenario_result"]
            story += [P(f"{o['name']} — index {o['total_score']}/100", "Heading3"),
                      P(f"Buyer: {o['buyer']}"), P(f"Problem: {o['problem']}"),
                      P(f"Test price: {_money(o['price'])} {o['price_model']} — {o['price_rationale']}"),
                      P(f"Contribution per sale {_money(sr['unit_contribution'])}; break-even {sr['breakeven_units']} sales (assumptions)."),
                      P(f"Validation: {o['validation_plan']}"),
                      P("Risks: " + "; ".join(o.get("risks") or [])),
                      P("Missing evidence: " + "; ".join(o.get("missing_evidence") or []))]
    if d["experiments"]:
        story.append(P("Validation experiments", "Heading2"))
        for x in d["experiments"]:
            story.append(P(f"{x['name']}: {x['evaluation']['recommendation']} — {x['evaluation']['reason']}"))
    if an and an.get("unknowns"):
        story.append(P("Important unknowns", "Heading2"))
        story += [P("• " + u) for u in an["unknowns"]]
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      title=a["name"]).build(story)


def build(audience_id: str) -> dict:
    d = gather(audience_id)
    rid = db.new_id("rp")
    folder = config.REPORTS_DIR / rid
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w]+", "_", d["audience"]["name"]).strip("_")[:40] or "report"
    files = {"html": folder / f"{slug}.html", "pdf": folder / f"{slug}.pdf", "json": folder / f"{slug}.json",
             "opportunities_csv": folder / f"{slug}_opportunities.csv", "signals_csv": folder / f"{slug}_signals.csv"}
    files["html"].write_text(render_html(d))
    render_pdf(d, files["pdf"])
    files["json"].write_text(json.dumps(d, indent=2, default=str))
    with open(files["opportunities_csv"], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "product_type", "buyer", "problem", "price", "price_model", "index_0_100",
                    "production_cost", "fulfillment_cost_per_unit", "status", "evidence_count"])
        for o in d["opportunities"]:
            w.writerow([o["name"], o["product_type"], o["buyer"], o["problem"], o["price"], o["price_model"],
                        o["total_score"], o["production_cost"], o["fulfillment_cost_per_unit"], o["status"], len(o["evidence"])])
    with open(files["signals_csv"], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["problem", "signal_type", "intent_level", "summary", "quote", "platform", "source", "locator"])
        labels = {c["id"]: c["label"] for c in d["intelligence"]["clusters"]}
        an = d["intelligence"]["analysis"]
        if an:
            for s in intel.signal_rows(an["id"], limit=100000):
                w.writerow([labels.get(s["cluster_id"], ""), s["signal_type"], s["intent_level"], s["summary"],
                            s["quote"], s["platform"], s["source_title"], s["locator"]])
    with db.tx() as c:
        db.insert(c, "reports", {"id": rid, "audience_id": audience_id, "kind": "research",
                                 "title": f"{d['audience']['name']} — research report",
                                 "files_json": {k: str(v) for k, v in files.items()}, "created_at": db.now()})
        db.log_activity(c, audience_id, "report", "Exported research report (HTML, PDF, JSON, CSV)")
    return db.one("SELECT * FROM reports WHERE id=?", (rid,))
