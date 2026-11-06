"""API: post-pilot money features — payout file, PDF statement, creator portal, next-test suggestions, checkout sync."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db
from ..services import agency, checkout_sync, optimize, statements
from .core import must
from .monetize import PREVIEW_CSP, product_full

r = APIRouter(prefix="/api")


def _statement(org_id: str, start=None, end=None) -> dict:
    must(db.one("SELECT id FROM organizations WHERE id=?", (org_id,)), "Creator")
    return agency.statement(org_id, start or None, end or None)


@r.get("/payouts/due")
def payouts_due(include_demo: bool = False):
    rows = statements.payout_rows(include_demo)
    return {"rows": rows, "total": round(sum(float(x["amount"]) for x in rows), 2),
            "missing_email": [x["creator"] for x in rows if x["missing_email"]]}


@r.get("/payouts/export.csv")
def payouts_csv(include_demo: bool = False):
    path, rows = statements.payout_csv(include_demo)
    return FileResponse(path, filename=path.name, media_type="text/csv")


@r.get("/creators/{org_id}/statement.pdf")
def statement_pdf(org_id: str, start: str | None = None, end: str | None = None):
    st = _statement(org_id, start, end)
    path = statements.statement_pdf(st)
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@r.get("/creators/{org_id}/portal")
def portal(org_id: str, download: bool = False):
    path = statements.write_portal(_statement(org_id))
    return FileResponse(path, filename=path.name if download else None, media_type="text/html",
                        headers={"Content-Security-Policy": PREVIEW_CSP},
                        content_disposition_type="attachment" if download else "inline")


@r.get("/products/{pid}/next-tests")
def next_tests(pid: str):
    p = product_full(pid)
    return {"suggestions": optimize.suggestions(p), "prices_tested": optimize.tested_prices(p)}


@r.get("/optimize")
def optimize_overview(include_demo: bool = False):
    ps = db.all_("SELECT * FROM products WHERE status IN ('launched','paused')" + ("" if include_demo else " AND is_demo=0"))
    out = []
    for p in ps:
        full = product_full(p["id"])
        out.append({"product_id": p["id"], "product": p["name"], "org_name": full["org_name"],
                    "suggestions": optimize.suggestions(full)})
    for p in ps:
        p["pnl"] = agency.product_pnl(p)
    return {"products": optimize.compare_products(ps), "suggestions": out}


class SyncConfig(BaseModel):
    sync_provider: str | None = Field(default=None, pattern="^(stripe|gumroad|shopify|lemonsqueezy)$")
    sync_ref: str | None = Field(default=None, max_length=200)


@r.put("/products/{pid}/sync")
def set_sync(pid: str, body: SyncConfig):
    product_full(pid)
    ref = (body.sync_ref or "").strip() or None
    if body.sync_provider == "stripe" and ref and not ref.startswith("plink_"):
        raise HTTPException(400, "Stripe Payment Link IDs start with plink_ (Stripe → Payment Links → the link → ID).")
    if body.sync_provider == "shopify" and ref:
        try:
            ref = "/".join(checkout_sync.parse_shopify_ref(ref))
        except checkout_sync.SyncError as e:
            raise HTTPException(400, str(e))
    with db.tx() as c:
        db.update(c, "products", pid, {"sync_provider": body.sync_provider, "sync_ref": ref if body.sync_provider else None,
                                       "updated_at": db.now()})
    return product_full(pid)


@r.post("/products/{pid}/sync")
def run_sync(pid: str):
    product_full(pid)
    try:
        result = checkout_sync.sync_product(pid)
    except checkout_sync.SyncError as e:
        raise HTTPException(400, str(e))
    return {"result": result, "product": product_full(pid)}
