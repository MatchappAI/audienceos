"""End-to-end API flow with the rules engine (no AI model needed), plus the agency revenue-share flow."""
from pathlib import Path

from app import config, settings_store

from .conftest import drain

COMMENTS = "\n".join([
    "Where can I buy that banneton? Link please",
    "I'd pay for a step by step course, the free videos are scattered",
    "My starter always collapses after day 5, so frustrated",
    "My starter always collapses after day 5, so frustrated",
    "Check out my profile and DM me for deals",
    "How do you schedule baking around a 9-5 job?",
    "I bought a $40 ebook and it didn't work",
])


def test_security_guards(client):
    from fastapi.testclient import TestClient

    from app import main
    raw = TestClient(main.app)
    assert raw.post("/api/audiences", json={"org_name": "x"}).status_code == 403  # no CSRF header
    assert raw.get("/api/health", headers={"host": "evil.example"}).status_code == 403  # DNS rebinding


def test_full_research_flow(client):
    settings_store.set_many({"ai_provider": "rules"})
    a = client.post("/api/audiences", json={"org_name": "Test Baker", "channels": [
        {"platform": "instagram", "handle": "@t", "follower_count": 5000}]}).json()
    aid = a["id"]
    assert a["audience_size"] == 5000

    r = client.post(f"/api/audiences/{aid}/sources/text", json={"text": COMMENTS, "as_comments": True, "platform": "instagram"})
    assert r.status_code == 200
    dup = client.post(f"/api/audiences/{aid}/sources/text", json={"text": COMMENTS, "as_comments": True}).json()
    assert dup["duplicate"] is True
    client.post(f"/api/audiences/{aid}/sources/upload", files={"files": ("evil.pdf", b"MZ\x90binary", "application/pdf")})
    up = client.post(f"/api/audiences/{aid}/sources/upload", data={"platform": "newsletter"},
                     files={"files": ("issue.md", b"# Issue\nReaders keep asking how to keep a starter alive while travelling.",
                                      "text/markdown")}).json()
    assert up["files"][0]["kind"] == "text"
    drain()
    srcs = client.get(f"/api/audiences/{aid}/sources").json()
    assert all(s["status"] == "ready" for s in srcs), srcs
    comments = next(s for s in srcs if s["comments"])
    assert any("duplicate" in o for o in comments["obtained"]) and any("spam" in o for o in comments["obtained"])

    r = client.post(f"/api/audiences/{aid}/analyze", json={})
    assert r.status_code == 200
    drain()
    intel = client.get(f"/api/audiences/{aid}/intelligence").json()
    an = intel["analysis"]
    assert an and an["status"] == "done" and an["provider"] == "rules"
    assert an["stats"]["duplicates_excluded"] == 1 and an["stats"]["spam_excluded"] == 1
    assert intel["clusters"] and intel["purchasing"]
    assert any("rules engine" in u for u in an["unknowns"])
    q = intel["purchasing"][0]
    ev = client.get(f"/api/evidence/{q['evidence_id']}").json()
    assert ev["quote"] in ev["comment"]["text"]  # evidence is verbatim from the stored comment
    # Rules engine never invents product ideas
    assert client.get(f"/api/opportunities?audience_id={aid}").json() == []

    rep = client.post(f"/api/audiences/{aid}/reports").json()
    for k in ("html", "pdf", "json", "opportunities_csv", "signals_csv"):
        assert Path(rep["files"][k]).exists()
    assert client.get(f"/api/reports/{rep['id']}/html").status_code == 200

    lib = client.get("/api/library", params={"q": "banneton"}).json()
    assert lib["comments"] and lib["evidence"]
    assert Path(client.post("/api/backup").json()["path"]).exists()
    dash = client.get("/api/dashboard").json()
    assert dash["stats"]["audiences"] >= 1


def test_external_provider_needs_key_and_consent(client):
    a = client.post("/api/audiences", json={"org_name": "Ext"}).json()
    r = client.post(f"/api/audiences/{a['id']}/analyze", json={"provider": "anthropic"})
    assert r.status_code == 400 and "key" in r.json()["detail"].lower()
    settings_store.set_secret("anthropic_api_key", "sk-test")
    settings_store.set_many({"allow_external_ai": True})
    r = client.post(f"/api/audiences/{a['id']}/analyze", json={"provider": "anthropic"})
    assert r.status_code == 409  # must confirm data leaves the Mac
    settings_store.set_secret("anthropic_api_key", None)
    settings_store.set_many({"allow_external_ai": False})


def test_offline_mode_reports_url_failure(client):
    settings_store.set_many({"allow_web_retrieval": False})
    a = client.post("/api/audiences", json={"org_name": "Offline"}).json()
    client.post(f"/api/audiences/{a['id']}/sources/urls", json={"urls": ["https://example.com/post"]})
    drain()
    s = client.get(f"/api/audiences/{a['id']}/sources").json()[0]
    assert s["status"] == "failed" and any("turned off" in m for m in s["missing"])
    settings_store.set_many({"allow_web_retrieval": True})


def test_instagram_url_is_honestly_unsupported(client):
    a = client.post("/api/audiences", json={"org_name": "IG"}).json()
    client.post(f"/api/audiences/{a['id']}/sources/urls", json={"urls": ["https://www.instagram.com/p/abc/"]})
    drain()
    s = client.get(f"/api/audiences/{a['id']}/sources").json()[0]
    assert s["status"] == "unsupported" and s["alternatives"]


def test_experiment_csv_import_is_idempotent(client):
    a = client.post("/api/audiences", json={"org_name": "Exp"}).json()
    x = client.post("/api/experiments", json={"audience_id": a["id"], "name": "T", "price": 39,
                                              "criteria": [{"metric": "purchases", "op": ">=", "value": 3}]}).json()
    csv = (config.FIXTURES_DIR / "demo" / "orders_demo.csv").read_bytes()
    r1 = client.post(f"/api/experiments/{x['id']}/import", files={"file": ("o.csv", csv, "text/csv")}).json()
    r2 = client.post(f"/api/experiments/{x['id']}/import", files={"file": ("o.csv", csv, "text/csv")}).json()
    assert r1["result"]["imported"] == 5 and r2["result"]["imported"] == 0
    v = r2["experiment"]["metrics"]["values"]
    assert v["purchases"] == 5 and v["net_sales"] == 156.0 and v["payment_fees"] == 7.15
    d = client.post(f"/api/experiments/{x['id']}/decision", json={"decision": "go"}).json()
    assert d["decision"] == "go" and d["status"] == "completed"


def test_agency_revenue_share_and_launch_gate(client):
    a = client.post("/api/audiences", json={"org_name": "Pilot Creator"}).json()
    org = a["org_id"]
    p = client.post("/api/products", json={"audience_id": a["id"], "name": "Kit", "price": 39}).json()
    full = {k["key"]: True for k in p["checklist"]}
    assert client.post(f"/api/products/{p['id']}/launch").status_code == 400  # not approved
    assert client.post(f"/api/products/{p['id']}/approve", json={"checklist": full, "approver": "M"}).status_code == 400  # no checkout
    assert client.patch(f"/api/products/{p['id']}", json={"checkout_url": "http://insecure"}).status_code == 400
    client.patch(f"/api/products/{p['id']}", json={"checkout_url": "https://x.gumroad.com/l/kit"})
    assert client.post(f"/api/products/{p['id']}/approve", json={"checklist": full, "approver": "M"}).json()["status"] == "approved"
    assert client.post(f"/api/products/{p['id']}/launch").json()["status"] == "launched"
    for ref, amt, refd in (("o1", 100, 0), ("o2", 100, 100)):
        client.post(f"/api/products/{p['id']}/sales", json={"order_ref": ref, "amount": amt, "refunded_amount": refd, "fee": 3})
    assert client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "o1", "amount": 1}).status_code == 409
    client.post(f"/api/products/{p['id']}/costs", json={"amount": 14, "category": "ads", "shared": True})
    client.post(f"/api/products/{p['id']}/costs", json={"amount": 5, "category": "tools", "shared": False})
    st = client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "contribution"}).json()
    # net 100, fees 6, shared costs 14 -> base 80 -> creator 56, agency 24 (agency also bears its own $5)
    assert st["totals"]["split_base"] == 80 and st["totals"]["creator_share"] == 56 and st["totals"]["agency_share"] == 24
    assert st["totals"]["agency_net_after_own_costs"] == 19
    st = client.post(f"/api/creators/{org}/payouts", json={"date": "2026-11-01", "amount": 50}).json()
    assert st["balance_owed"] == 6
    st = client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "net_sales"}).json()
    assert st["totals"]["creator_share"] == 65.8  # (100-6)*0.7
    # Changing the price of a launched product requires re-approval
    back = client.patch(f"/api/products/{p['id']}", json={"price": 49}).json()
    assert back["status"] == "draft"
    # ...and the UI is told why, with the sales history intact (bug 3)
    assert back["reapproval"]["fields"] == ["price"] and back["reapproval"]["from_status"] == "launched"
    assert back["reapproval"]["previous_approver"] == "M" and "re-approve" in back["reapproval"]["message"]
    assert back["pnl"]["orders"] == 2 and len(back["sales"]) == 2
    listed = {x["id"]: x for x in client.get("/api/products", params={"audience_id": a["id"]}).json()}
    assert listed[p["id"]]["reapproval"]["fields"] == ["price"]
    # A never-approved draft carries no re-approval notice
    fresh = client.post("/api/products", json={"audience_id": a["id"], "name": "New"}).json()
    assert fresh["reapproval"] is None
    # Re-approving relaunches cleanly
    assert client.post(f"/api/products/{p['id']}/approve", json={"checklist": full, "approver": "M"}).json()["reapproval"] is None
    stages = {c["id"]: c["stage"] for c in client.get("/api/creators").json()["creators"]}
    assert stages[org] == "selling"


def test_migrations_idempotent():
    from app import db
    assert db.migrate() == []


def test_library_content_results_link_to_their_source(client):
    a = client.post("/api/audiences", json={"org_name": "Library Creator"}).json()
    r = client.post(f"/api/audiences/{a['id']}/sources/text",
                    json={"title": "Hydration notes", "text": "Zebrafinch hydration at altitude needs less water."})
    assert r.status_code == 200, r.text
    drain()
    res = client.get("/api/library", params={"q": "Zebrafinch", "kind": "content"}).json()
    assert res["content"], res
    src_ids = {s["id"] for s in client.get(f"/api/audiences/{a['id']}/sources").json()}
    assert all(x["source_id"] in src_ids for x in res["content"])


def test_auto_hypothesis_reads_cleanly(client):
    from app.routers.monetize import hypothesis_for
    h = hypothesis_for({"buyer": "Home bakers (T1).", "price": 50, "name": "Coaching", "problem": "Wants troubleshooting (T2, E4)."})
    assert h == "Home bakers will pay $50 for Coaching. Problem it solves: Wants troubleshooting."


def test_statement_csv_formats_money_and_counts(client):
    a = client.post("/api/audiences", json={"org_name": "CSV Creator"}).json()
    p = client.post("/api/products", json={"audience_id": a["id"], "name": "Kit", "price": 10}).json()
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "c1", "amount": 10, "fee": 0.6})
    client.post(f"/api/creators/{a['org_id']}/deal", json={"creator_share_pct": 70, "basis": "net_sales"})
    rows = client.get(f"/api/creators/{a['org_id']}/statement.csv").text.splitlines()
    total = next(r for r in rows if r.startswith("TOTAL")).split(",")
    assert total[1] == "1" and total[2] == "10.00" and total[-3] == "6.58"  # (10-0.6)*0.7


def test_interrupted_analysis_and_its_ai_runs_are_closed_out(client):
    from app import db
    settings_store.set_many({"ai_provider": "rules"})
    a = client.post("/api/audiences", json={"org_name": "Crash Creator"}).json()
    client.post(f"/api/audiences/{a['id']}/sources/text", json={"text": COMMENTS, "as_comments": True})
    drain()
    stale, run = db.new_id("an"), db.new_id("run")
    with db.tx() as c:  # what a quit mid-analysis leaves behind
        db.insert(c, "analyses", {"id": stale, "audience_id": a["id"], "provider": "ollama", "status": "running", "started_at": db.now()})
        db.insert(c, "ai_runs", {"id": run, "audience_id": a["id"], "analysis_id": stale, "stage": "2 · extraction",
                                 "provider": "ollama", "status": "running", "started_at": db.now()})
    client.post(f"/api/audiences/{a['id']}/analyze", json={})
    drain()
    assert db.scalar("SELECT status FROM analyses WHERE id=?", (stale,)) == "failed"
    assert db.scalar("SELECT status FROM ai_runs WHERE id=?", (run,)) == "failed"
    assert db.scalar("SELECT status FROM analyses WHERE audience_id=? ORDER BY started_at DESC, rowid DESC LIMIT 1", (a["id"],)) == "done"


def test_api_keys_never_returned_or_logged(client, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    secret = "sk-ant-TESTSECRET-1234567890abcdef"
    assert client.put("/api/secrets/anthropic_api_key", json={"value": secret}).json() == {"saved": True, "name": "anthropic_api_key"}
    try:
        for path in ("/api/system", "/api/dashboard"):
            assert secret not in client.get(path).text
        assert secret not in caplog.text
    finally:
        client.put("/api/secrets/anthropic_api_key", json={"value": None})


def test_landing_copy_patch_still_accepts_copy_field(client):
    from app import db
    a = client.post("/api/audiences", json={"org_name": "Copy Creator"}).json()
    oid, aid = db.new_id("op"), db.new_id("as")
    with db.tx() as c:
        db.insert(c, "opportunities", {"id": oid, "audience_id": a["id"], "name": "Kit", "status": "proposed",
                                       "created_at": db.now(), "updated_at": db.now()})
        db.insert(c, "assets", {"id": aid, "opportunity_id": oid, "audience_id": a["id"], "kind": "landing_page",
                                "title": "LP", "content": "x", "data_json": {"copy": {"headline": "Old"}},
                                "status": "approved", "created_at": db.now(), "updated_at": db.now()})
    r = client.patch(f"/api/assets/{aid}", json={"copy": {"headline": "New"}})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["copy"]["headline"] == "New" and r.json()["status"] == "draft"


def test_deleting_an_audience_removes_its_files(client):
    from app import config, db
    a = client.post("/api/audiences", json={"org_name": "Files Creator"}).json()
    client.post(f"/api/audiences/{a['id']}/sources/text", json={"text": "How do I feed my starter on holiday?"})
    drain()
    sid = client.get(f"/api/audiences/{a['id']}/sources").json()[0]["id"]
    rid = db.new_id("rp")
    with db.tx() as c:
        db.insert(c, "reports", {"id": rid, "audience_id": a["id"], "kind": "research", "title": "r", "created_at": db.now()})
    for d in (config.MEDIA_DIR / sid, config.REPORTS_DIR / rid, config.UPLOADS_DIR / a["id"]):
        d.mkdir(parents=True, exist_ok=True)
        (d / "f.txt").write_text("x")
    assert client.delete(f"/api/audiences/{a['id']}").json() == {"deleted": True}
    for d in (config.MEDIA_DIR / sid, config.REPORTS_DIR / rid, config.UPLOADS_DIR / a["id"]):
        assert not d.exists(), d


def test_dashboard_says_analysis_is_running(client):
    """While an analysis is queued/running, the next action must not ask the user to start it again."""
    a = client.post("/api/audiences", json={"org_name": "Running Check"}).json()
    client.post(f"/api/audiences/{a['id']}/sources/text", json={"title": "Note", "text": "People ask how to keep a starter alive."})
    drain()
    client.post(f"/api/audiences/{a['id']}/analyze", json={})  # queued, not drained
    acts = [x["text"] for x in client.get("/api/dashboard").json()["next_actions"] if "Running Check" in x["text"]]
    assert acts and acts[0].startswith("Analysis running") and not any("Run the first analysis" in t for t in acts)
    drain()
    client.delete(f"/api/audiences/{a['id']}")


def test_unhandled_error_hides_exception_text(client):
    from fastapi.routing import APIRoute

    from app import main

    def boom():
        raise RuntimeError("secret /Users/someone/path SELECT * FROM t")

    main.app.router.routes.insert(0, APIRoute("/api/__boom_test", boom, methods=["GET"]))
    try:
        from fastapi.testclient import TestClient
        with TestClient(main.app, raise_server_exceptions=False) as c:
            r = c.get("/api/__boom_test")
        assert r.status_code == 500
        detail = r.json()["detail"]
        assert "error id" in detail
        assert "secret" not in detail and "SELECT" not in detail
    finally:
        main.app.router.routes.pop(0)

