"""API: opportunities, competitors, experiments, assets, reports, and agency operations (deals, products, sales, payouts)."""
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .. import config, db, jobs
from ..ai.rules import strip_refs
from ..ingest.store import parse_date, pick
from ..services import agency, assets, competitors, economics, experiments as ex, reports, scoring
from .core import must

r = APIRouter(prefix="/api")


# ---------- opportunities ----------

def opp_full(oid: str) -> dict:
    o = must(db.one("SELECT o.*, a.name AS audience_name, a.is_demo FROM opportunities o JOIN audiences a ON a.id=o.audience_id "
                    "WHERE o.id=?", (oid,)), "Opportunity")
    o["evidence"] = db.all_("""SELECT e.id, e.quote, e.locator, s.title AS source_title, s.platform, s.original_url,
        (SELECT intent_level FROM signals sg WHERE sg.evidence_id=e.id LIMIT 1) AS intent_level
        FROM evidence e JOIN opportunity_evidence oe ON oe.evidence_id=e.id LEFT JOIN sources s ON s.id=e.source_id
        WHERE oe.opportunity_id=?""", (oid,))
    ids = o.get("cluster_ids") or []
    o["clusters"] = db.all_(f"SELECT id, label, description, unique_authors, intent_score, evidence_quality FROM clusters "
                            f"WHERE id IN ({','.join('?' for _ in ids) or 'NULL'})", tuple(ids))
    o["score_breakdown"] = scoring.explain(o.get("scores") or {})
    o["scenario_result"] = economics.scenario(o["price"], o["fulfillment_cost_per_unit"], o["production_cost"], o.get("scenario") or {})
    o["competitors"] = db.all_("SELECT * FROM competitors WHERE audience_id=? AND (opportunity_id=? OR opportunity_id IS NULL) "
                               "ORDER BY created_at DESC", (o["audience_id"], oid))
    o["experiments"] = db.all_("SELECT id, name, status, decision FROM experiments WHERE opportunity_id=?", (oid,))
    o["products"] = db.all_("SELECT id, name, status FROM products WHERE opportunity_id=?", (oid,))
    o["assets"] = db.all_("SELECT id, kind, title, status, created_at FROM assets WHERE opportunity_id=? ORDER BY created_at DESC", (oid,))
    o["run"] = db.one("SELECT provider, model, external, finished_at FROM ai_runs WHERE id=?", (o["ai_run_id"],)) if o.get("ai_run_id") else None
    return o


@r.get("/opportunities")
def list_opps(audience_id: str | None = None, status: str | None = None):
    where, params = ["1=1"], []
    if audience_id:
        where.append("o.audience_id=?")
        params.append(audience_id)
    if status:
        where.append("o.status=?")
        params.append(status)
    return db.all_(f"""SELECT o.id, o.audience_id, o.analysis_id, o.name, o.buyer, o.problem, o.product_type, o.price, o.price_model,
        o.total_score, o.status, o.delivery_difficulty, o.recurring, o.missing_evidence_json, o.created_at, a.name AS audience_name, a.is_demo,
        (SELECT COUNT(*) FROM opportunity_evidence oe WHERE oe.opportunity_id=o.id) AS evidence_count,
        (SELECT a2.id FROM analyses a2 WHERE a2.audience_id=o.audience_id AND a2.status='done' ORDER BY started_at DESC LIMIT 1) = o.analysis_id AS is_latest
        FROM opportunities o JOIN audiences a ON a.id=o.audience_id WHERE {' AND '.join(where)}
        ORDER BY is_latest DESC, o.total_score DESC""", tuple(params))


@r.get("/opportunities/{oid}")
def get_opp(oid: str):
    return opp_full(oid)


class OppPatch(BaseModel):
    name: str | None = None
    status: str | None = Field(default=None, pattern="^(proposed|approved|testing|validated|rejected)$")
    price: float | None = Field(default=None, ge=0)
    production_cost: float | None = Field(default=None, ge=0)
    fulfillment_cost_per_unit: float | None = Field(default=None, ge=0)
    scenario: dict | None = None
    scores: dict | None = None


@r.patch("/opportunities/{oid}")
def patch_opp(oid: str, body: OppPatch):
    o = must(db.one("SELECT * FROM opportunities WHERE id=?", (oid,)), "Opportunity")
    d = body.model_dump(exclude_none=True)
    if "scenario" in d:
        d["scenario_json"] = d.pop("scenario")
    if "scores" in d:
        s = {**(o.get("scores") or {}), **{k: max(1, min(5, int(v))) for k, v in d.pop("scores").items()}}
        d["scores_json"] = s
        d["total_score"] = scoring.total(s)
    with db.tx() as c:
        db.update(c, "opportunities", oid, {**d, "updated_at": db.now()})
        if body.status:
            db.log_activity(c, o["audience_id"], "opportunity", f"'{o['name']}' marked {body.status}")
    return opp_full(oid)


# ---------- competitors ----------

class CompetitorIn(BaseModel):
    name: str = Field(min_length=1)
    url: str | None = None
    price_text: str | None = None
    opportunity_id: str | None = None


@r.get("/audiences/{aid}/competitors")
def list_comp(aid: str):
    return db.all_("SELECT * FROM competitors WHERE audience_id=? ORDER BY created_at DESC", (aid,))


@r.post("/audiences/{aid}/competitors")
def add_comp(aid: str, body: CompetitorIn):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    url = body.url.strip() if body.url else None
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return competitors.add(aid, body.name, url, body.price_text, body.opportunity_id)


@r.delete("/competitors/{cid}")
def del_comp(cid: str):
    with db.tx() as c:
        c.execute("DELETE FROM competitors WHERE id=?", (cid,))
    return {"deleted": True}


@r.post("/opportunities/{oid}/research")
def research(oid: str):
    o = must(db.one("SELECT * FROM opportunities WHERE id=?", (oid,)), "Opportunity")
    return {"job_id": jobs.enqueue("competitor_search", o["audience_id"], oid, {"opportunity_id": oid}, max_attempts=1)}


# ---------- experiments ----------

class ExperimentIn(BaseModel):
    opportunity_id: str | None = None
    audience_id: str | None = None
    name: str | None = None
    hypothesis: str | None = None
    target_audience: str | None = None
    offer: str | None = None
    price: float | None = Field(default=None, ge=0)
    channel: str | None = None
    target_exposure: int | None = Field(default=None, ge=0)
    criteria: list[dict] | None = None
    start_date: str | None = None
    end_date: str | None = None
    payment_fee_pct: float | None = Field(default=None, ge=0, le=100)
    payment_fee_fixed: float | None = Field(default=None, ge=0)
    checkout_url: str | None = None
    attribution_notes: str | None = None
    findings: str | None = None
    next_action: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|running|completed)$")


def exp_full(xid: str) -> dict:
    x = must(db.one("SELECT x.*, a.name AS audience_name, o.name AS opportunity_name FROM experiments x "
                    "JOIN audiences a ON a.id=x.audience_id LEFT JOIN opportunities o ON o.id=x.opportunity_id WHERE x.id=?",
                    (xid,)), "Experiment")
    x["events"] = db.all_("SELECT * FROM experiment_events WHERE experiment_id=? ORDER BY date, created_at", (xid,))
    x["orders"] = db.all_("SELECT * FROM orders WHERE experiment_id=? ORDER BY date", (xid,))
    m = ex.compute(x, x["events"], x["orders"])
    x["metrics"], x["evaluation"] = m, ex.evaluate(x, m)
    x["assets"] = db.all_("SELECT id, kind, title, status, created_at FROM assets WHERE experiment_id=? OR "
                          "(opportunity_id=? AND experiment_id IS NULL) ORDER BY created_at DESC", (xid, x["opportunity_id"]))
    x["metric_options"] = [{"key": k, "label": v[0], "unit": v[2]} for k, v in ex.METRIC_DEFS.items()]
    return x


@r.get("/experiments")
def list_exps(audience_id: str | None = None):
    rows = db.all_("SELECT x.*, a.name AS audience_name, o.name AS opportunity_name FROM experiments x "
                   "JOIN audiences a ON a.id=x.audience_id LEFT JOIN opportunities o ON o.id=x.opportunity_id "
                   + ("WHERE x.audience_id=? " if audience_id else "") + "ORDER BY x.created_at DESC",
                   (audience_id,) if audience_id else ())
    for x in rows:
        m = ex.compute(x, db.all_("SELECT * FROM experiment_events WHERE experiment_id=?", (x["id"],)),
                       db.all_("SELECT * FROM orders WHERE experiment_id=?", (x["id"],)))
        x["summary"] = {k: m["values"][k] for k in ("purchases", "net_sales", "purchase_conversion", "contribution_margin")}
        x["visits"] = m["totals"]["landing_visits"]
        x["recommendation"] = ex.evaluate(x, m)["recommendation"]
    return rows


@r.post("/experiments")
def create_exp(body: ExperimentIn):
    o = db.one("SELECT * FROM opportunities WHERE id=?", (body.opportunity_id,)) if body.opportunity_id else None
    aid = o["audience_id"] if o else body.audience_id
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    d = body.model_dump(exclude_none=True)
    d.pop("audience_id", None)
    crit = d.pop("criteria", None)
    if crit is None and o and o["price"]:
        crit = [{"metric": "purchase_conversion", "op": ">=", "value": ""}, {"metric": "purchases", "op": ">=", "value": ""}]
    rec = {"id": db.new_id("ex"), "audience_id": aid, "name": d.pop("name", None) or (f"Test: {o['name']}" if o else "New experiment"),
           "hypothesis": d.pop("hypothesis", None) or (hypothesis_for(o) if o else None),
           "target_audience": d.pop("target_audience", None) or (o["buyer"] if o else None),
           "offer": d.pop("offer", None) or (o["name"] if o else None),
           "price": d.pop("price", None) if body.price is not None else (o["price"] if o else None),
           "criteria_json": crit or [], "payment_fee_pct": d.pop("payment_fee_pct", 2.9), "payment_fee_fixed": d.pop("payment_fee_fixed", 0.30),
           "status": "draft", "is_demo": db.scalar("SELECT is_demo FROM audiences WHERE id=?", (aid,)) or 0,
           "created_at": db.now(), "updated_at": db.now(), **d}
    with db.tx() as c:
        db.insert(c, "experiments", rec)
        if o and o["status"] in ("proposed", "approved"):
            c.execute("UPDATE opportunities SET status='testing', updated_at=? WHERE id=?", (db.now(), o["id"]))
        db.log_activity(c, aid, "experiment", f"Created experiment '{rec['name']}'")
    return exp_full(rec["id"])


@r.get("/experiments/{xid}")
def get_exp(xid: str):
    return exp_full(xid)


@r.patch("/experiments/{xid}")
def patch_exp(xid: str, body: ExperimentIn):
    must(db.one("SELECT id FROM experiments WHERE id=?", (xid,)), "Experiment")
    d = body.model_dump(exclude_unset=True)
    d.pop("opportunity_id", None)
    d.pop("audience_id", None)
    if "criteria" in d:
        d["criteria_json"] = d.pop("criteria") or []
    if d.get("checkout_url") and not re.match(r"^https://", d["checkout_url"]):
        raise HTTPException(400, "Checkout links must start with https://")
    with db.tx() as c:
        db.update(c, "experiments", xid, {**d, "updated_at": db.now()})
    return exp_full(xid)


@r.delete("/experiments/{xid}")
def delete_exp(xid: str):
    with db.tx() as c:
        c.execute("DELETE FROM experiments WHERE id=?", (xid,))
    return {"deleted": True}


class EventIn(BaseModel):
    date: str | None = None
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    landing_visits: int | None = Field(default=None, ge=0)
    checkout_visits: int | None = Field(default=None, ge=0)
    purchases: int | None = Field(default=None, ge=0)
    gross_revenue: float | None = Field(default=None, ge=0)
    refunds: int | None = Field(default=None, ge=0)
    refund_amount: float | None = Field(default=None, ge=0)
    payment_fees: float | None = Field(default=None, ge=0)
    other_costs: float | None = Field(default=None, ge=0)
    note: str | None = None


@r.post("/experiments/{xid}/events")
def add_event(xid: str, body: EventIn):
    must(db.one("SELECT id FROM experiments WHERE id=?", (xid,)), "Experiment")
    d = body.model_dump()
    if all(v is None for k, v in d.items() if k not in ("date", "note")):
        raise HTTPException(400, "Enter at least one number.")
    with db.tx() as c:
        db.insert(c, "experiment_events", {"id": db.new_id("ee"), "experiment_id": xid, "origin": "manual",
                                           "created_at": db.now(), **d})
    return exp_full(xid)


@r.delete("/events/{eid}")
def del_event(eid: str):
    e = must(db.one("SELECT experiment_id FROM experiment_events WHERE id=?", (eid,)), "Result row")
    with db.tx() as c:
        c.execute("DELETE FROM experiment_events WHERE id=?", (eid,))
    return exp_full(e["experiment_id"])


@r.delete("/orders/{oid}")
def del_order(oid: str):
    o = must(db.one("SELECT experiment_id FROM orders WHERE id=?", (oid,)), "Order")
    with db.tx() as c:
        c.execute("DELETE FROM orders WHERE id=?", (oid,))
    return exp_full(o["experiment_id"])


async def _read_csv(f: UploadFile) -> str:
    raw = await f.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(400, "CSV is larger than 20 MB.")
    if b"\x00" in raw[:4096]:
        raise HTTPException(400, "That doesn't look like a CSV file.")
    return raw.decode("utf-8-sig", errors="replace")


@r.post("/experiments/{xid}/import")
async def import_exp(xid: str, file: UploadFile = File(...)):
    must(db.one("SELECT id FROM experiments WHERE id=?", (xid,)), "Experiment")
    res = ex.import_csv(xid, await _read_csv(file))
    return {"result": res, "experiment": exp_full(xid)}


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(go|revise|stop)$")
    note: str | None = None


@r.post("/experiments/{xid}/decision")
def decide(xid: str, body: DecisionIn):
    x = exp_full(xid)
    with db.tx() as c:
        db.update(c, "experiments", xid, {"decision": body.decision, "decision_note": body.note, "status": "completed",
                                          "updated_at": db.now()})
        if x["opportunity_id"]:
            st = {"go": "validated", "stop": "rejected", "revise": "testing"}[body.decision]
            c.execute("UPDATE opportunities SET status=?, updated_at=? WHERE id=?", (st, db.now(), x["opportunity_id"]))
        db.log_activity(c, x["audience_id"], "decision",
                        f"Decision on '{x['name']}': {body.decision.upper()} (app recommended: {x['evaluation']['recommendation']})")
    return exp_full(xid)


@r.get("/experiments-compare")
def compare(ids: str):
    out = []
    for xid in ids.split(",")[:6]:
        x = exp_full(xid.strip())
        out.append({"id": x["id"], "name": x["name"], "price": x["price"], "channel": x["channel"],
                    "totals": x["metrics"]["totals"], "values": x["metrics"]["values"],
                    "ci": x["metrics"]["purchase_conversion_ci95"], "recommendation": x["evaluation"]["recommendation"]})
    return out


# ---------- assets ----------

@r.get("/asset-kinds")
def asset_kinds():
    return assets.ASSET_KINDS


class GenIn(BaseModel):
    opportunity_id: str
    experiment_id: str | None = None
    kind: str
    instructions: str | None = None


@r.post("/assets/generate")
def gen_asset(body: GenIn):
    o = must(db.one("SELECT * FROM opportunities WHERE id=?", (body.opportunity_id,)), "Opportunity")
    if body.kind not in assets.ASSET_KINDS:
        raise HTTPException(400, "Unknown asset type")
    from ..ai import providers
    p = providers.get_provider()
    ok, why = p.available()
    if not ok or not p.is_llm:
        raise HTTPException(400, why if not ok else "Writing drafts needs an AI model. Choose the local model in Settings.")
    return {"job_id": jobs.enqueue("generate_asset", o["audience_id"], None, body.model_dump(), max_attempts=1,
                                   message="Drafting")}


@r.get("/assets")
def list_assets(opportunity_id: str | None = None, experiment_id: str | None = None, audience_id: str | None = None):
    where, params = ["1=1"], []
    for k, v in (("opportunity_id", opportunity_id), ("experiment_id", experiment_id), ("audience_id", audience_id)):
        if v:
            where.append(f"{k}=?")
            params.append(v)
    return db.all_(f"SELECT id, audience_id, opportunity_id, experiment_id, kind, title, status, created_at FROM assets "
                   f"WHERE {' AND '.join(where)} ORDER BY created_at DESC", tuple(params))


@r.get("/assets/{aid}")
def get_asset(aid: str):
    a = must(db.one("SELECT * FROM assets WHERE id=?", (aid,)), "Asset")
    a["html"] = assets.render_markdown(a["content"])
    return a


class AssetPatch(BaseModel):
    title: str | None = None
    content: str | None = None
    landing_copy: dict | None = Field(default=None, alias="copy")  # API field stays "copy"; renamed to avoid shadowing BaseModel.copy


@r.patch("/assets/{aid}")
def patch_asset(aid: str, body: AssetPatch):
    a = must(db.one("SELECT * FROM assets WHERE id=?", (aid,)), "Asset")
    d = {k: v for k, v in body.model_dump(exclude_none=True).items() if k in ("title", "content")}
    if body.landing_copy is not None and a["kind"] == "landing_page":
        d["data_json"] = {**(a.get("data") or {}), "copy": body.landing_copy}
    if "content" in d or "data_json" in d:
        d["review_json"] = {"flags": assets.rule_flags(d.get("content", a["content"])),
                            "overall": "Edited by you — rule-based check re-run; run a new draft for an AI review."}
        d["status"], d["approved_at"] = "draft", None  # edits require re-approval
    with db.tx() as c:
        db.update(c, "assets", aid, {**d, "updated_at": db.now()})
    return get_asset(aid)


class ApproveIn(BaseModel):
    approved: bool


@r.post("/assets/{aid}/approve")
def approve_asset(aid: str, body: ApproveIn):
    a = must(db.one("SELECT * FROM assets WHERE id=?", (aid,)), "Asset")
    with db.tx() as c:
        db.update(c, "assets", aid, {"status": "approved" if body.approved else "draft",
                                     "approved_at": db.now() if body.approved else None, "updated_at": db.now()})
        db.log_activity(c, a["audience_id"], "asset", f"{'Approved' if body.approved else 'Unapproved'} '{a['title']}'")
    return get_asset(aid)


@r.delete("/assets/{aid}")
def del_asset(aid: str):
    with db.tx() as c:
        c.execute("DELETE FROM assets WHERE id=?", (aid,))
    return {"deleted": True}


PREVIEW_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'"


@r.get("/assets/{aid}/preview", response_class=HTMLResponse)
def preview_asset(aid: str):
    a = must(db.one("SELECT * FROM assets WHERE id=?", (aid,)), "Asset")
    csp = PREVIEW_CSP + ("; script-src 'unsafe-inline'" if a["kind"] == "calculator" else "")
    return HTMLResponse(assets.asset_html(a), headers={"Content-Security-Policy": csp})


@r.get("/assets/{aid}/export")
def export_asset(aid: str, format: str = "md"):
    a = must(db.one("SELECT * FROM assets WHERE id=?", (aid,)), "Asset")
    if format not in ("md", "html", "docx"):
        raise HTTPException(400, "Format must be md, html or docx")
    p = assets.export_asset(a, format)
    return FileResponse(p, filename=p.name)


# ---------- reports ----------

@r.post("/audiences/{aid}/reports")
def make_report(aid: str):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    return reports.build(aid)


@r.get("/audiences/{aid}/reports")
def list_reports(aid: str):
    return db.all_("SELECT * FROM reports WHERE audience_id=? ORDER BY created_at DESC", (aid,))


@r.get("/reports/{rid}/{key}")
def report_file(rid: str, key: str, download: bool = False):
    rp = must(db.one("SELECT * FROM reports WHERE id=?", (rid,)), "Report")
    path = (rp.get("files") or {}).get(key)
    if not path or not Path(path).exists():
        raise HTTPException(404, "File not found")
    p = Path(path).resolve()
    if not str(p).startswith(str(config.REPORTS_DIR.resolve())):
        raise HTTPException(403, "Not allowed")
    headers = {"Content-Security-Policy": PREVIEW_CSP} if p.suffix == ".html" else {}
    return FileResponse(p, filename=p.name if download else None, headers=headers,
                        content_disposition_type="attachment" if download else "inline")


# ---------- agency: creators, deals, products, sales, costs, payouts ----------

@r.get("/creators")
def creators():
    out = db.all_("SELECT o.*, (SELECT COUNT(*) FROM audiences a WHERE a.organization_id=o.id) AS audiences "
                  "FROM organizations o ORDER BY o.updated_at DESC")
    for o in out:
        o["stage"] = agency.stage(o["id"])
        o["stage_label"] = agency.STAGE_LABEL[o["stage"]]
        o["deal"] = agency.active_deal(o["id"])
        st = agency.statement(o["id"])
        o["totals"], o["balance_owed"] = st["totals"], st["balance_owed"]
        o["audience_ids"] = [a["id"] for a in db.all_("SELECT id FROM audiences WHERE organization_id=?", (o["id"],))]
    return {"creators": out, "stages": [{"key": k, "label": agency.STAGE_LABEL[k]} for k in agency.STAGES]}


class OrgPatch(BaseModel):
    contact_name: str | None = None
    contact_email: str | None = None
    description: str | None = None


@r.patch("/creators/{org_id}")
def patch_creator(org_id: str, body: OrgPatch):
    must(db.one("SELECT id FROM organizations WHERE id=?", (org_id,)), "Creator")
    with db.tx() as c:
        db.update(c, "organizations", org_id, {**body.model_dump(exclude_none=True), "updated_at": db.now()})
    return agency.statement(org_id)


class DealIn(BaseModel):
    creator_share_pct: float = Field(ge=0, le=100)
    basis: str = Field(pattern="^(net_sales|contribution)$")
    start_date: str | None = None
    end_date: str | None = None
    notes: str | None = None
    loss_carry_forward: bool = False
    min_guarantee_monthly: float | None = Field(default=None, ge=0)
    guarantee_months: int | None = Field(default=None, gt=0)


@r.post("/creators/{org_id}/deal")
def set_deal(org_id: str, body: DealIn):
    must(db.one("SELECT id FROM organizations WHERE id=?", (org_id,)), "Creator")
    with db.tx() as c:
        c.execute("UPDATE deals SET status='ended', updated_at=? WHERE organization_id=? AND status='active'", (db.now(), org_id))
        db.insert(c, "deals", {"id": db.new_id("dl"), "organization_id": org_id, "status": "active",
                               "created_at": db.now(), "updated_at": db.now(),
                               **{**body.model_dump(), "loss_carry_forward": int(body.loss_carry_forward),
                                  "min_guarantee_monthly": body.min_guarantee_monthly or None}})
        aid = c.execute("SELECT id FROM audiences WHERE organization_id=? LIMIT 1", (org_id,)).fetchone()
        db.log_activity(c, aid[0] if aid else None, "deal",
                        f"Deal set: creator {body.creator_share_pct:g}% / agency {100 - body.creator_share_pct:g}% of {body.basis.replace('_', ' ')}")
    return agency.statement(org_id)


@r.get("/creators/{org_id}/statement")
def creator_statement(org_id: str, start: str | None = None, end: str | None = None):
    must(db.one("SELECT id FROM organizations WHERE id=?", (org_id,)), "Creator")
    return agency.statement(org_id, start or None, end or None)


@r.get("/creators/{org_id}/statement.csv")
def creator_statement_csv(org_id: str, start: str | None = None, end: str | None = None):
    import csv
    st = creator_statement(org_id, start, end)
    path = config.EXPORTS_DIR / f"statement_{org_id}.csv"
    cols = ["product", "orders", "gross", "refunds", "net_sales", "fees", "shared_costs", "split_base", "creator_share",
            "agency_share", "agency_only_costs"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"Creator statement — {st['organization']['name']}",
                    f"Period: {start or 'all time'} to {end or 'today'}",
                    f"Deal: creator {st['deal']['creator_share_pct']:g}% of {st['deal']['basis']}" if st["deal"] else "No deal"])
        w.writerow(cols)

        def cell(c, v):  # whole order counts, money to the cent; blank when not computable (no deal)
            if v is None or v == "":
                return ""
            return int(v) if c == "orders" else f"{float(v):.2f}"
        for l in st["lines"]:
            w.writerow([l["product"]] + [cell(c, l.get(c)) for c in cols[1:]])
        w.writerow(["TOTAL"] + [cell(c, st["totals"].get(c)) for c in cols[1:]])
        w.writerow([])
        w.writerow(["All-time creator share", cell("x", st["all_time_creator_share"])])
        w.writerow(["Paid out", cell("x", st["paid_out"])])
        w.writerow(["Balance owed to creator", cell("x", st["balance_owed"])])
    return FileResponse(path, filename=f"{st['organization']['name']} statement.csv".replace("/", "_"))


class PayoutIn(BaseModel):
    date: str
    amount: float = Field(gt=0)
    reference: str | None = None
    note: str | None = None


@r.post("/creators/{org_id}/payouts")
def add_payout(org_id: str, body: PayoutIn):
    must(db.one("SELECT id FROM organizations WHERE id=?", (org_id,)), "Creator")
    with db.tx() as c:
        db.insert(c, "payouts", {"id": db.new_id("po"), "organization_id": org_id, "created_at": db.now(), **body.model_dump()})
    return agency.statement(org_id)


@r.delete("/payouts/{pid}")
def del_payout(pid: str):
    p = must(db.one("SELECT organization_id FROM payouts WHERE id=?", (pid,)), "Payout")
    with db.tx() as c:
        c.execute("DELETE FROM payouts WHERE id=?", (pid,))
    return agency.statement(p["organization_id"])


def hypothesis_for(o: dict) -> str:
    """'<buyer> will pay $X for <name>. Problem it solves: <problem>' — readable whatever form the model wrote them in."""
    buyer = strip_refs((o.get("buyer") or "This audience").strip().rstrip("."))
    problem = strip_refs((o.get("problem") or "").strip())
    price = f"${o['price']:g}" if o.get("price") is not None else "the test price"
    return f"{buyer} will pay {price} for {o['name']}." + (f" Problem it solves: {problem}" if problem else "")


class ProductIn(BaseModel):
    opportunity_id: str | None = None
    audience_id: str | None = None
    experiment_id: str | None = None
    name: str | None = None
    product_type: str | None = None
    price: float | None = Field(default=None, ge=0)
    price_model: str | None = None
    storefront: str | None = None
    checkout_url: str | None = None
    notes: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|paused|retired)$")


FIELD_LABELS = {"name": "name", "price": "price", "price_model": "pricing model", "checkout_url": "checkout link"}


def reapproval_info(p: dict) -> dict | None:
    """Why a product that has been approved/launched before is a draft again (None for a never-approved draft)."""
    if p["status"] != "draft":
        return None
    reset = (p.get("approval") or {}).get("reset")
    sold = (p.get("pnl") or {}).get("orders") or 0
    if not reset and not p.get("launched_at") and not sold:
        return None
    fields = [FIELD_LABELS.get(f, f) for f in (reset or {}).get("fields", [])]
    what = "/".join(fields) if fields else "price/name/link"
    was = (reset or {}).get("from_status") or ("launched" if p.get("launched_at") else "approved")
    return {"fields": fields, "from_status": was, "at": (reset or {}).get("at"),
            "previous_approver": (reset or {}).get("previous_approver"),
            "message": f"Back to draft — {what} changed after {'launch' if was == 'launched' else 'approval'}; "
                       f"re-approve to relaunch. Sales history is kept."}


def product_full(pid: str) -> dict:
    p = must(db.one("SELECT p.*, a.name AS audience_name, a.organization_id, o.name AS org_name FROM products p "
                    "JOIN audiences a ON a.id=p.audience_id JOIN organizations o ON o.id=a.organization_id WHERE p.id=?",
                    (pid,)), "Product")
    p["pnl"] = agency.product_pnl(p)
    p["sales"] = db.all_("SELECT * FROM product_sales WHERE product_id=? ORDER BY date DESC, created_at DESC LIMIT 500", (pid,))
    p["costs"] = db.all_("SELECT * FROM product_costs WHERE product_id=? ORDER BY date DESC", (pid,))
    full = db.all_("SELECT id, kind, title, status, content, data_json FROM assets WHERE opportunity_id=?",
                   (p["opportunity_id"],)) if p["opportunity_id"] else []
    p["assets"] = [{k: a[k] for k in ("id", "kind", "title", "status")} for a in full]
    # Assets are drafted at the test price; warn before launch when their text quotes another amount.
    p["asset_warnings"] = [{"asset_id": a["id"], "title": a["title"], "amounts": amts}
                           for a in full if (amts := assets.price_mismatches(a, p.get("price")))]
    p["checklist"] = [{"key": k, "label": l, "done": bool((p.get("approval") or {}).get("checklist", {}).get(k))}
                      for k, l in agency.LAUNCH_CHECKLIST]
    p["deal"] = agency.active_deal(p["organization_id"])
    p["reapproval"] = reapproval_info(p)
    return p


@r.get("/products")
def list_products(audience_id: str | None = None):
    rows = db.all_("SELECT p.*, a.name AS audience_name, o.name AS org_name FROM products p JOIN audiences a ON a.id=p.audience_id "
                   "JOIN organizations o ON o.id=a.organization_id " + ("WHERE p.audience_id=? " if audience_id else "") +
                   "ORDER BY p.created_at DESC", (audience_id,) if audience_id else ())
    for p in rows:
        p["pnl"] = agency.product_pnl(p)
        p["reapproval"] = reapproval_info(p)
    return rows


@r.post("/products")
def create_product(body: ProductIn):
    o = db.one("SELECT * FROM opportunities WHERE id=?", (body.opportunity_id,)) if body.opportunity_id else None
    aid = o["audience_id"] if o else body.audience_id
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    if body.checkout_url and not body.checkout_url.startswith("https://"):
        raise HTTPException(400, "Checkout links must start with https://")
    pid = db.new_id("pr")
    with db.tx() as c:
        db.insert(c, "products", {
            "id": pid, "audience_id": aid, "opportunity_id": o["id"] if o else None, "experiment_id": body.experiment_id,
            "name": body.name or (o["name"] if o else "New product"), "product_type": body.product_type or (o["product_type"] if o else None),
            "price": body.price if body.price is not None else (o["price"] if o else None),
            "price_model": body.price_model or (o["price_model"] if o else "one-time"),
            "storefront": body.storefront, "checkout_url": body.checkout_url, "notes": body.notes, "status": "draft",
            "is_demo": db.scalar("SELECT is_demo FROM audiences WHERE id=?", (aid,)) or 0,
            "created_at": db.now(), "updated_at": db.now()})
        db.log_activity(c, aid, "product", f"Created product '{body.name or (o['name'] if o else 'New product')}' (draft)")
    return product_full(pid)


@r.get("/products/{pid}")
def get_product(pid: str):
    return product_full(pid)


@r.patch("/products/{pid}")
def patch_product(pid: str, body: ProductIn):
    p = product_full(pid)
    d = body.model_dump(exclude_unset=True)
    for k in ("opportunity_id", "audience_id"):
        d.pop(k, None)
    if d.get("checkout_url") and not d["checkout_url"].startswith("https://"):
        raise HTTPException(400, "Checkout links must start with https://")
    material = {"name", "price", "price_model", "checkout_url"} & set(d)
    changed = [k for k in ("name", "price", "price_model", "checkout_url") if k in material and d[k] != p[k]]
    if p["status"] in ("approved", "launched", "paused") and changed:
        # Changing what buyers see requires a fresh approval. Record why, so the UI can explain it.
        d["status"], d["approved_at"] = "draft", None
        d["approval_json"] = {"reset": {"fields": changed, "from_status": p["status"], "at": db.now(),
                                        "previous_approver": (p.get("approval") or {}).get("approver")}}
    with db.tx() as c:
        db.update(c, "products", pid, {**d, "updated_at": db.now()})
    return product_full(pid)


class ApprovalIn(BaseModel):
    checklist: dict[str, bool]
    approver: str = Field(min_length=1, max_length=100)
    note: str | None = None


@r.post("/products/{pid}/approve")
def approve_product(pid: str, body: ApprovalIn):
    p = product_full(pid)
    missing = [l for k, l in agency.LAUNCH_CHECKLIST if not body.checklist.get(k)]
    if missing:
        raise HTTPException(400, "Every launch check must be confirmed: " + "; ".join(missing))
    if not p["checkout_url"]:
        raise HTTPException(400, "Add the external checkout link before approving.")
    unapproved = [a["title"] for a in p["assets"] if a["status"] != "approved"]
    if unapproved:
        raise HTTPException(400, "These marketing assets are still drafts: " + "; ".join(unapproved[:5]))
    with db.tx() as c:
        db.update(c, "products", pid, {"status": "approved", "approved_at": db.now(), "updated_at": db.now(),
                                       "approval_json": {"checklist": body.checklist, "approver": body.approver,
                                                         "note": body.note, "at": db.now()}})
        db.log_activity(c, p["audience_id"], "product", f"'{p['name']}' approved for launch by {body.approver}")
    return product_full(pid)


@r.post("/products/{pid}/launch")
def launch_product(pid: str):
    p = product_full(pid)
    if p["status"] not in ("approved", "paused"):
        raise HTTPException(400, "Only approved products can be marked launched.")
    with db.tx() as c:
        db.update(c, "products", pid, {"status": "launched", "launched_at": p["launched_at"] or db.now(), "updated_at": db.now()})
        if p["opportunity_id"]:
            c.execute("UPDATE opportunities SET status='validated' WHERE id=? AND status IN ('approved','testing','proposed')", (p["opportunity_id"],))
        db.log_activity(c, p["audience_id"], "product", f"'{p['name']}' marked launched (you published it on {p['storefront'] or 'the storefront'})")
    return product_full(pid)


class SaleIn(BaseModel):
    order_ref: str = Field(min_length=1)
    date: str | None = None
    amount: float = Field(ge=0)
    refunded_amount: float = Field(default=0, ge=0)
    fee: float | None = Field(default=None, ge=0)
    channel: str | None = None


@r.post("/products/{pid}/sales")
def add_sale(pid: str, body: SaleIn):
    product_full(pid)
    with db.tx() as c:
        cur = c.execute("INSERT OR IGNORE INTO product_sales (id, product_id, order_ref, date, amount, refunded_amount, fee, channel, origin, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)", (db.new_id("ps"), pid, body.order_ref.strip(), body.date, body.amount,
                                                         body.refunded_amount, body.fee, body.channel, "manual", db.now()))
    if not cur.rowcount:
        raise HTTPException(409, "An order with that ID is already recorded.")
    return product_full(pid)


CHANNEL_KEYS = ("channel", "utm_source", "source", "referrer", "utm_campaign", "attribution")


@r.post("/products/{pid}/sales/import")
async def import_sales(pid: str, file: UploadFile = File(...)):
    p = product_full(pid)
    rows = ex.parse_csv(await _read_csv(file))
    if not rows or not (set(rows[0]) & set(ex.ORDER_ID)) or not (set(rows[0]) & set(ex.ORDER_AMT)):
        raise HTTPException(400, "The CSV needs an order ID column (e.g. id, order_id, sale_id) and an amount column "
                                 "(e.g. amount, total, price). Export orders from your checkout (Stripe, Gumroad, Shopify…).")
    imported = dup = 0
    errors = []
    with db.tx() as c:
        for i, rr in enumerate(rows, 2):
            oid, amt = pick(rr, ex.ORDER_ID), ex._num(pick(rr, ex.ORDER_AMT))
            if not oid or amt is None:
                errors.append(f"Row {i}: missing order ID or amount")
                continue
            refv = pick(rr, ex.ORDER_REF)
            ref_amt = ex._num(refv)
            if ref_amt is None and str(refv).lower() in ("true", "yes", "1"):
                ref_amt = amt
            cur = c.execute("INSERT OR IGNORE INTO product_sales (id, product_id, order_ref, date, amount, refunded_amount, fee, channel, origin, created_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)", (db.new_id("ps"), pid, str(oid), parse_date(pick(rr, ex.ORDER_DATE)), amt,
                                                             ref_amt or 0, ex._num(pick(rr, ex.ORDER_FEE)),
                                                             (str(pick(rr, CHANNEL_KEYS))[:80] if pick(rr, CHANNEL_KEYS) else None), "csv", db.now()))
            imported += cur.rowcount
            dup += 1 - cur.rowcount
        db.log_activity(c, p["audience_id"], "sales", f"Imported {imported} orders for '{p['name']}'")
    return {"result": {"imported": imported, "skipped_duplicates": dup, "errors": errors[:20]}, "product": product_full(pid)}


@r.delete("/sales/{sid}")
def del_sale(sid: str):
    s = must(db.one("SELECT product_id FROM product_sales WHERE id=?", (sid,)), "Sale")
    with db.tx() as c:
        c.execute("DELETE FROM product_sales WHERE id=?", (sid,))
    return product_full(s["product_id"])


class CostIn(BaseModel):
    date: str | None = None
    category: str = Field(default="other", pattern="^(production|ads|tools|fulfillment|contractor|other)$")
    amount: float = Field(ge=0)
    shared: bool = True
    note: str | None = None


@r.post("/products/{pid}/costs")
def add_cost(pid: str, body: CostIn):
    product_full(pid)
    with db.tx() as c:
        db.insert(c, "product_costs", {"id": db.new_id("pc"), "product_id": pid, "created_at": db.now(),
                                       **{**body.model_dump(), "shared": int(body.shared)}})
    return product_full(pid)


@r.delete("/costs/{cid}")
def del_cost(cid: str):
    s = must(db.one("SELECT product_id FROM product_costs WHERE id=?", (cid,)), "Cost")
    with db.tx() as c:
        c.execute("DELETE FROM product_costs WHERE id=?", (cid,))
    return product_full(s["product_id"])
