"""Product-creation and marketing asset workflows: structured generation, then claim review.

Nothing is published or sent anywhere. Assets stay drafts until the user approves them.
"""
import html
import json
import re
from pathlib import Path

import bleach
import markdown as md

from .. import config, db, jobs
from ..ai import providers, schemas

ASSET_KINDS = {
    "offer": "Test offer (one-page summary of what is sold, to whom, at what price, and the promise)",
    "landing_page": "Landing page copy",
    "newsletter": "Newsletter promotion email announcing the offer",
    "social": "Social promotion: one 30-45 second short-video script and three post captions",
    "sample": "A genuinely useful free sample or prototype of the product (e.g. one module, one template section)",
    "description": "Product description for a store listing",
    "outline": "Detailed product outline (modules/sections and what each delivers)",
    "checklist": "A practical checklist the buyer can use",
    "workbook": "A workbook with exercises and prompts",
    "guide": "A concise how-to guide section",
    "email_campaign": "A 4-email launch sequence (subject + body for each)",
    "spec": "Product specification: scope, deliverables, format, production steps, support needs",
    "calculator": "A simple calculator tool",
}

RULES = ("Rules: Do not promise results, income, health outcomes or guarantees. No invented testimonials, statistics, "
         "scarcity or credentials. Use [brackets] for anything the creator must fill in (their story, real numbers, "
         "links). Be specific, useful and plain-spoken. Write in the creator's voice where possible.")

RISKY = [
    (r"\bguarantee[sd]?\b", "Guarantee language — only keep if you actually offer one"),
    (r"\b(100|\d{2,3})\s?%", "Specific percentage — must be backed by real data"),
    (r"\b(proven|scientifically|clinically|doctor[- ]approved)\b", "Proof claim — needs a citation"),
    (r"\$\s?\d[\d,]*\s?(/|per)\s?(month|mo|year|week)", "Income/savings figure — remove unless documented"),
    (r"\b(cure|heal|treat|diagnos)\w*", "Health claim — high legal risk"),
    (r"\b(only \d+ (left|spots)|limited time|ends tonight|last chance)\b", "Scarcity — only use if true"),
    (r"\b(best|#1|number one|world'?s (best|first))\b", "Superlative — hard to substantiate"),
    (r"\b(testimonial|\"[^\"]{10,}\" ?[-—] ?[A-Z][a-z]+)", "Possible testimonial — must be real and permissioned"),
    # Live run: the 7B model wrote a made-up website for the demo creator. Contact details must come from the creator.
    (r"(https?://[^\s)\]]+|\bwww\.[^\s)\]]+|\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b|\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b)",
     "Link, email or phone number — the model may have invented it; replace with the creator's real one"),
]


def context_for(opp: dict, exp: dict | None) -> str:
    ev = db.all_("SELECT e.quote FROM evidence e JOIN opportunity_evidence oe ON oe.evidence_id=e.id "
                 "WHERE oe.opportunity_id=? LIMIT 8", (opp["id"],))
    org = db.one("SELECT o.name FROM organizations o JOIN audiences a ON a.organization_id=o.id WHERE a.id=?",
                 (opp["audience_id"],))
    price = exp["price"] if exp and exp.get("price") is not None else opp.get("price")
    parts = [f"Creator/business: {org['name'] if org else ''}", f"Product: {opp['name']} ({opp['product_type']})",
             f"Buyer: {opp['buyer']}", f"Problem solved: {opp['problem']}", f"Test price: ${price} {opp.get('price_model') or ''}",
             f"What gets produced: {opp['production']}"]
    if exp:
        parts += [f"Experiment offer: {exp.get('offer') or ''}", f"Channel: {exp.get('channel') or ''}"]
    parts.append("Audience quotes (verbatim, from research — may be used to reflect their language, never as testimonials):\n"
                 + "\n".join(f"- \"{e['quote'][:200]}\"" for e in ev))
    return "<source_material>\n" + "\n".join(parts) + "\n</source_material>"


def rule_flags(text: str) -> list[dict]:
    out = []
    for pat, why in RISKY:
        for m in re.finditer(pat, text, re.I):
            snippet = text[max(0, m.start() - 40): m.end() + 40].replace("\n", " ")
            out.append({"claim": snippet.strip(), "problem": why, "suggestion": "Verify, soften or remove", "by": "rules"})
            break
    return out


def review(provider, text: str) -> dict:
    flags = rule_flags(text)
    model_review = None
    try:
        r = provider.complete_json(
            "You are a strict compliance editor. Find claims in this marketing/product draft that are unsupported, "
            "exaggerated, legally risky, or that invent facts (testimonials, statistics, credentials, results). "
            "Return an empty list if there are none.",
            f"<source_material>\n{text[:12000]}\n</source_material>", schemas.ClaimReview, max_tokens=1500)
        model_review = r.overall
        flags += [{**i.model_dump(), "by": "AI review"} for i in r.issues]
    except Exception as e:
        model_review = f"AI review unavailable: {str(e)[:120]}"
    return {"flags": flags[:30], "overall": model_review}


SAFE_EXPR = re.compile(r"^[\w\s+\-*/().]+$")


def validate_calculator(spec: dict) -> dict:
    names = []
    for i in spec.get("inputs", []):
        n = re.sub(r"\W", "_", str(i.get("name", "")).strip().lower())
        if not n or not re.match(r"^[a-z_]\w*$", n):
            continue
        try:
            dflt = float(i.get("default") or 0)
        except ValueError:
            dflt = 0
        names.append({"name": n, "label": str(i.get("label") or n)[:80], "default": dflt})
    allowed = {x["name"] for x in names}
    outs = []
    for o in spec.get("outputs", []):
        ex = str(o.get("expression", ""))
        idents = set(re.findall(r"[A-Za-z_]\w*", ex))
        if SAFE_EXPR.match(ex) and idents <= allowed:
            outs.append({"label": str(o.get("label") or "Result")[:80], "expression": ex})
    return {"inputs": names, "outputs": outs}


def calculator_html(title: str, desc: str, calc: dict) -> str:
    inputs = "\n".join(f'<label>{html.escape(i["label"])}<input type="number" step="any" id="{i["name"]}" value="{i["default"]}"></label>'
                       for i in calc["inputs"])
    outs = "\n".join(f'<div class="out"><span>{html.escape(o["label"])}</span><strong id="o{k}">–</strong></div>'
                     for k, o in enumerate(calc["outputs"]))
    # Expressions were validated to contain only declared input names, numbers and + - * / ( ).
    fns = "\n".join(f'  set("o{k}", (function({", ".join(i["name"] for i in calc["inputs"])}){{return {o["expression"]};}})({", ".join(f"v(\"{i["name"]}\")" for i in calc["inputs"])}));'
                    for k, o in enumerate(calc["outputs"]))
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 20px;color:#1d1d1f}}
label{{display:block;margin:12px 0;font-size:14px;color:#555}}input{{display:block;width:100%;padding:10px;font-size:16px;border:1px solid #ccc;border-radius:8px;margin-top:4px}}
.out{{display:flex;justify-content:space-between;padding:12px 0;border-top:1px solid #eee}}</style></head><body>
<h1>{html.escape(title)}</h1><p>{html.escape(desc)}</p>{inputs}<h2>Results</h2>{outs}
<script>
function v(id){{return parseFloat(document.getElementById(id).value)||0}}
function set(id,x){{document.getElementById(id).textContent=isFinite(x)?(Math.round(x*100)/100).toLocaleString():'–'}}
function calc(){{
{fns}
}}
document.querySelectorAll('input').forEach(function(e){{e.addEventListener('input',calc)}});calc();
</script></body></html>"""


def landing_html(copy: dict, price: float | None, checkout_url: str | None, approved: bool, title: str) -> str:
    e = lambda s: html.escape(str(s or ""))
    href = checkout_url if checkout_url and re.match(r"^https://", checkout_url) else "#checkout"
    banner = "" if approved else ('<div class="draft">DRAFT — not yet approved. Review every claim before publishing.</div>')
    nocheckout = "" if href != "#checkout" else ('<p class="note">No checkout link set. Add one on the product or experiment '
                                                  'before publishing — this page cannot take payments by itself.</p>')
    li = lambda xs: "".join(f"<li>{e(x)}</li>" for x in xs)
    # A 7B model often writes the call to action as a sentence; a sentence is not a button label.
    cta_raw = (copy.get("cta") or "").strip()
    cta_long = len(cta_raw) > 40 or cta_raw.count(" ") > 6
    cta = (f"Get it — ${price:,.0f}" if price else "Get it") if cta_long or not cta_raw else cta_raw
    cta_lead = f'<p class="lead">{e(cta_raw)}</p>' if cta_long else ""
    faq = "".join(f"<details><summary>{e(f.get('q'))}</summary><p>{e(f.get('a'))}</p></details>" for f in copy.get("faq", []))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
:root{{--ink:#1d1d1f;--sub:#6e6e73;--line:#e5e5ea;--accent:#0a66c2}}
*{{box-sizing:border-box}}body{{margin:0;font:17px/1.6 -apple-system,BlinkMacSystemFont,"Inter",system-ui,sans-serif;color:var(--ink);background:#fff}}
.wrap{{max-width:720px;margin:0 auto;padding:56px 24px}}h1{{font-size:44px;line-height:1.1;letter-spacing:-.02em;margin:0 0 16px}}
.sub{{font-size:21px;color:var(--sub);margin:0 0 32px}}h2{{font-size:24px;margin:48px 0 12px}}ul{{padding-left:20px}}li{{margin:6px 0}}
.cta{{display:inline-block;background:var(--ink);color:#fff;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:600}}
.lead{{font-size:18px;margin:0 0 18px}}.price{{font-size:28px;font-weight:700;margin:24px 0 8px}}.box{{border:1px solid var(--line);border-radius:16px;padding:24px;margin-top:40px}}
details{{border-top:1px solid var(--line);padding:14px 0}}summary{{cursor:pointer;font-weight:600}}
.draft{{background:#fff4ce;color:#5c4400;text-align:center;padding:10px;font-size:14px;font-weight:600}}.note{{color:#b42318;font-size:14px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}@media(max-width:640px){{.two{{grid-template-columns:1fr}}h1{{font-size:34px}}}}
</style></head><body>{banner}<div class="wrap">
<h1>{e(copy.get('headline'))}</h1><p class="sub">{e(copy.get('subheadline'))}</p>
{cta_lead}<a class="cta" href="{e(href)}">{e(cta)}</a>{nocheckout}
<h2>The problem</h2><p>{e(copy.get('problem'))}</p>
<h2>What this does for you</h2><ul>{li(copy.get('bullets', []))}</ul>
<h2>What's inside</h2><ul>{li(copy.get('whats_inside', []))}</ul>
<div class="two"><div><h2>Who it's for</h2><p>{e(copy.get('who_its_for'))}</p></div><div><h2>Who it's not for</h2><p>{e(copy.get('who_its_not_for'))}</p></div></div>
<div class="box"><div class="price">{e(copy.get('price_line') or (f'${price:,.2f}' if price is not None else ''))}</div>
<a class="cta" href="{e(href)}">{e(cta)}</a></div>
{'<h2>Questions</h2>' + faq if faq else ''}
</div></body></html>"""


def render_markdown(text: str) -> str:
    raw = md.markdown(text, extensions=["tables", "sane_lists"])
    return bleach.clean(raw, tags=["p", "h1", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "blockquote", "code",
                                   "pre", "table", "thead", "tbody", "tr", "th", "td", "hr", "br", "a"],
                        attributes={"a": ["href"]}, protocols=["https", "http", "mailto"], strip=True)


@jobs.handler("generate_asset")
def generate_asset(job, progress):
    p = jobs.payload(job)
    kind = p["kind"]
    if kind not in ASSET_KINDS:
        raise ValueError("Unknown asset type")
    opp = db.one("SELECT * FROM opportunities WHERE id=?", (p["opportunity_id"],))
    exp = db.one("SELECT * FROM experiments WHERE id=?", (p["experiment_id"],)) if p.get("experiment_id") else None
    provider = providers.require(providers.get_provider())
    if not provider.is_llm:
        raise providers.ProviderUnavailable("Writing drafts needs an AI model. Choose the local model in Settings.")
    ctx = context_for(opp, exp)
    rid = db.new_id("run")
    with db.tx() as c:
        db.insert(c, "ai_runs", {"id": rid, "audience_id": opp["audience_id"], "stage": f"asset · {kind}",
                                 "provider": provider.name, "model": provider.model, "external": int(provider.external),
                                 "input_chars": len(ctx), "status": "running", "started_at": db.now()})
    progress(0.1, "Drafting")
    data, title = {}, f"{ASSET_KINDS[kind].split('(')[0].strip()} — {opp['name']}"
    extra = (p.get("instructions") or "").strip()[:1000]
    instr = f"\nAdditional direction from the user: {extra}" if extra else ""
    try:
        if kind == "landing_page":
            copy = provider.complete_json(f"Write landing-page copy for a product validation test. {RULES}",
                                          ctx + instr, schemas.LandingCopy, max_tokens=2500)
            data = {"copy": copy.model_dump()}
            content = "\n\n".join([f"# {copy.headline}", copy.subheadline, "## The problem", copy.problem,
                                   "## What this does for you", *[f"- {b}" for b in copy.bullets],
                                   "## What's inside", *[f"- {b}" for b in copy.whats_inside],
                                   f"**Who it's for:** {copy.who_its_for}", f"**Who it's not for:** {copy.who_its_not_for}",
                                   f"**{copy.price_line}** — {copy.cta}",
                                   "## FAQ", *[f"**{f.q}**\n\n{f.a}" for f in copy.faq]])
        elif kind == "calculator":
            spec = provider.complete_json(
                "Design a simple, genuinely useful calculator for this audience's problem. Inputs are numbers. Output "
                "expressions may use ONLY the input names, numbers and + - * / ( ). " + RULES,
                ctx + instr, schemas.CalculatorSpec, max_tokens=1500)
            calc = validate_calculator(spec.model_dump())
            if not calc["outputs"]:
                raise ValueError("The model's calculator formulas failed safety validation; try again.")
            data = {"calculator": calc, "title": spec.title, "description": spec.description}
            title = spec.title
            content = (f"# {spec.title}\n\n{spec.description}\n\n## Inputs\n" +
                       "\n".join(f"- {i['label']} (`{i['name']}`, default {i['default']})" for i in calc["inputs"]) +
                       "\n\n## Formulas\n" + "\n".join(f"- {o['label']} = `{o['expression']}`" for o in calc["outputs"]) +
                       f"\n\n{spec.notes}")
        else:
            d = provider.complete_json(f"Create: {ASSET_KINDS[kind]}. Output Markdown. {RULES}", ctx + instr,
                                       schemas.AssetDraft, max_tokens=4000)
            title, content = d.title or title, d.markdown
        progress(0.7, "Reviewing claims")
        rv = review(provider, content)
    except Exception as e:
        with db.tx() as c:
            db.update(c, "ai_runs", rid, {"status": "failed", "error": str(e)[:500], "finished_at": db.now()})
        raise
    aid = db.new_id("as")
    with db.tx() as c:
        db.update(c, "ai_runs", rid, {"status": "done", "finished_at": db.now()})
        db.insert(c, "assets", {"id": aid, "audience_id": opp["audience_id"], "opportunity_id": opp["id"],
                                "experiment_id": exp["id"] if exp else None, "kind": kind, "title": title[:200],
                                "content": content, "data_json": data, "review_json": rv, "status": "draft",
                                "ai_run_id": rid, "created_at": db.now(), "updated_at": db.now()})
        db.log_activity(c, opp["audience_id"], "asset", f"Drafted {kind.replace('_', ' ')} for '{opp['name']}'")
    with db.tx() as c:
        c.execute("UPDATE jobs SET ref_id=? WHERE id=?", (aid, job["id"]))
    return {"message": f"Draft ready ({len(rv['flags'])} claims to check)"}


def asset_html(asset: dict) -> str:
    data = asset.get("data") or {}
    if asset["kind"] == "landing_page" and data.get("copy"):
        exp = db.one("SELECT * FROM experiments WHERE id=?", (asset["experiment_id"],)) if asset.get("experiment_id") else None
        opp = db.one("SELECT * FROM opportunities WHERE id=?", (asset["opportunity_id"],))
        price = exp["price"] if exp and exp.get("price") is not None else (opp or {}).get("price")
        prod = db.one("SELECT price, checkout_url FROM products WHERE opportunity_id=? ORDER BY updated_at DESC LIMIT 1",
                      (asset["opportunity_id"],))
        # Live run: the page said "$50" while the product sold at $39. The product's price is what buyers pay.
        if prod and prod.get("price") is not None:
            price = prod["price"]
        link = (exp or {}).get("checkout_url") or (prod or {}).get("checkout_url")
        return landing_html(data["copy"], price, link,
                            asset["status"] == "approved", asset["title"])
    if asset["kind"] == "calculator" and data.get("calculator"):
        return calculator_html(data.get("title") or asset["title"], data.get("description") or "", data["calculator"])
    body = render_markdown(asset["content"])
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(asset['title'])}</title>"
            "<style>body{font:16px/1.65 -apple-system,system-ui,sans-serif;max-width:720px;margin:48px auto;padding:0 24px;"
            "color:#1d1d1f}h1,h2,h3{line-height:1.2}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}"
            "</style></head><body>" + body + "</body></html>")


def export_asset(asset: dict, fmt: str) -> Path:
    safe = re.sub(r"[^\w\- ]+", "", asset["title"])[:60].strip().replace(" ", "_") or asset["id"]
    out = config.EXPORTS_DIR / f"{safe}.{fmt}"
    if fmt == "md":
        out.write_text(asset["content"])
    elif fmt == "html":
        out.write_text(asset_html(asset))
    elif fmt == "docx":
        import docx
        d = docx.Document()
        for line in asset["content"].splitlines():
            s = line.rstrip()
            if s.startswith("### "):
                d.add_heading(s[4:], level=3)
            elif s.startswith("## "):
                d.add_heading(s[3:], level=2)
            elif s.startswith("# "):
                d.add_heading(s[2:], level=1)
            elif re.match(r"^\s*[-*] ", s):
                d.add_paragraph(re.sub(r"^\s*[-*] ", "", s).replace("**", ""), style="List Bullet")
            elif s:
                d.add_paragraph(s.replace("**", ""))
        d.save(str(out))
    else:
        raise ValueError("Unsupported format")
    return out


_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


def price_mismatches(asset: dict, price: float | None) -> list[str]:
    """Dollar amounts in an asset's text that differ from the product's price (e.g. a draft written at the test price)."""
    if price is None:
        return []
    data = asset.get("data") or {}
    text = " ".join([asset.get("content") or "", json.dumps(data.get("copy") or {}, ensure_ascii=False)])
    seen = []
    for m in _MONEY.finditer(text):
        v = float(m.group(1).replace(",", ""))
        label = f"${v:,.2f}".replace(".00", "")
        if abs(v - float(price)) > 0.005 and label not in seen:
            seen.append(label)
    return seen
