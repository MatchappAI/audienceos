"""Regression tests for the 2026-11-16 production-readiness audit."""
import threading

from app import db
from app.services import agency

FULL = {k: True for k, _ in agency.LAUNCH_CHECKLIST}


def _product(client, name, price=30):
    a = client.post("/api/audiences", json={"org_name": name}).json()
    p = client.post("/api/products", json={"audience_id": a["id"], "name": f"{name} kit", "price": price,
                                           "checkout_url": "https://x.example/kit"}).json()
    return a, p


def test_draft_cannot_skip_approval_via_pause(client):
    a, p = _product(client, "GateCo")
    r = client.patch(f"/api/products/{p['id']}", json={"status": "paused"})
    assert r.status_code == 400 and "Only a launched product" in r.text
    assert client.post(f"/api/products/{p['id']}/launch").status_code == 400
    assert client.get(f"/api/products/{p['id']}").json()["status"] == "draft"


def test_retired_product_must_be_reopened_and_reapproved(client):
    a, p = _product(client, "RetireCo")
    client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "M"})
    client.post(f"/api/products/{p['id']}/launch")
    assert client.patch(f"/api/products/{p['id']}", json={"status": "retired"}).json()["status"] == "retired"
    assert client.post(f"/api/products/{p['id']}/launch").status_code == 400
    r = client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "M"})
    assert r.status_code == 400 and "retired" in r.text
    back = client.patch(f"/api/products/{p['id']}", json={"status": "draft"}).json()
    assert back["status"] == "draft"
    assert client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "M"}).json()["status"] == "approved"


def test_pause_resume_keeps_approval_and_draft_withdraws_it(client):
    a, p = _product(client, "PauseCo")
    client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "M"})
    client.post(f"/api/products/{p['id']}/launch")
    assert client.patch(f"/api/products/{p['id']}", json={"status": "paused"}).json()["status"] == "paused"
    assert client.post(f"/api/products/{p['id']}/launch").json()["status"] == "launched"
    # Re-approving a live product is refused (it would silently demote it).
    assert client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "X"}).status_code == 400
    d = client.patch(f"/api/products/{p['id']}", json={"status": "draft"}).json()
    assert d["status"] == "draft" and d["approved_at"] is None and d["reapproval"]["from_status"] == "launched"


def test_flagged_asset_needs_confirmation_to_approve(client):
    a, p = _product(client, "FlagCo")
    with db.tx() as c:
        db.insert(c, "opportunities", {"id": "op_flagtest", "audience_id": a["id"], "name": "Flag kit", "status": "approved",
                                       "created_at": db.now(), "updated_at": db.now()})
        db.insert(c, "assets", {"id": "as_flagtest", "audience_id": a["id"], "opportunity_id": "op_flagtest", "kind": "offer",
                                "title": "Offer", "content": "Guaranteed results", "status": "draft",
                                "review_json": {"flags": [{"claim": "Guaranteed results", "problem": "guarantee"}]},
                                "created_at": db.now(), "updated_at": db.now()})
    r = client.post("/api/assets/as_flagtest/approve", json={"approved": True})
    assert r.status_code == 400 and "flagged claim" in r.text
    assert client.post("/api/assets/as_flagtest/approve", json={"approved": True, "flags_checked": True}).json()["status"] == "approved"
    assert client.post("/api/assets/as_flagtest/approve", json={"approved": False}).json()["status"] == "draft"


def test_owed_total_ignores_overpaid_creators(client):
    def creator(name, sale):
        a, p = _product(client, name)
        org = a["organization_id"]
        client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 50, "basis": "net_sales"})
        client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "o", "amount": sale, "fee": 0})
        return org
    before = client.get("/api/dashboard").json()["stats"]["creator_balance_owed"]
    owed = creator("OwedCo", 100)        # owed 50
    over = creator("OverpaidCo", 10)     # owed 5, then paid 40 → −35
    client.post(f"/api/creators/{over}/payouts", json={"date": "2026-11-01", "amount": 40})
    after = client.get("/api/dashboard").json()["stats"]["creator_balance_owed"]
    assert round(after - before, 2) == 50.0


def test_statement_warns_about_undated_out_of_term_and_changed_terms(client):
    a, p = _product(client, "WarnCo")
    org = a["organization_id"]
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "nodate", "amount": 10})
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "early", "amount": 10, "date": "2026-01-05"})
    client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "net_sales", "start_date": "2026-02-01"})
    st = client.get(f"/api/creators/{org}/statement", params={"start": "2026-01-01", "end": "2026-12-31"}).json()
    w = " ".join(st["warnings"])
    assert "no date" in w and "outside the deal term" in w and "terms were changed" not in w
    # Re-saving the same terms (e.g. a notes edit) isn't a change; a new percentage is.
    client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "net_sales", "start_date": "2026-02-01", "notes": "x"})
    assert "terms were changed" not in " ".join(client.get(f"/api/creators/{org}/statement").json()["warnings"])
    client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 60, "basis": "net_sales"})
    assert "terms were changed" in " ".join(client.get(f"/api/creators/{org}/statement").json()["warnings"])


def test_statement_line_back_to_draft_flag(client):
    a, p = _product(client, "LineCo")
    org = a["organization_id"]
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "s", "amount": 10})
    assert client.get(f"/api/creators/{org}/statement").json()["lines"][0]["back_to_draft"] is False
    client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "M"})
    client.patch(f"/api/products/{p['id']}", json={"price": 99})
    assert client.get(f"/api/creators/{org}/statement").json()["lines"][0]["back_to_draft"] is True


def test_creator_email_validated(client):
    a, p = _product(client, "MailCo")
    org = a["organization_id"]
    r = client.patch(f"/api/creators/{org}", json={"contact_email": "not-an-email"})
    assert r.status_code == 422 and "email" in r.text
    assert client.patch(f"/api/creators/{org}", json={"contact_email": " a@b.co "}).json()["organization"]["contact_email"] == "a@b.co"
    assert client.patch(f"/api/creators/{org}", json={"contact_email": ""}).status_code == 200


def test_experiment_dates_must_be_iso(client):
    a, p = _product(client, "ExpDateCo")
    r = client.post("/api/experiments", json={"audience_id": a["id"], "end_date": "next week"})
    assert r.status_code == 422
    x = client.post("/api/experiments", json={"audience_id": a["id"], "end_date": "2026-12-01"}).json()
    assert client.patch(f"/api/experiments/{x['id']}", json={"start_date": "12/01/2026"}).status_code == 422


def test_concurrent_analyze_starts_one_job(client, monkeypatch):
    from app.ai import providers
    a = client.post("/api/audiences", json={"org_name": "RaceCo"}).json()
    client.post(f"/api/audiences/{a['id']}/sources/text", json={"text": "I struggle with my starter", "as_comments": True})
    p = providers.get_provider("rules")
    monkeypatch.setattr(providers, "get_provider", lambda name=None: p)
    out = []
    ts = [threading.Thread(target=lambda: out.append(client.post(f"/api/audiences/{a['id']}/analyze", json={}).json()))
          for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len({o["job_id"] for o in out}) == 1
    assert db.scalar("SELECT COUNT(*) FROM jobs WHERE audience_id=? AND kind='analyze_audience'", (a["id"],)) == 1


def test_channel_patch_keeps_unsent_fields(client):
    a = client.post("/api/audiences", json={"org_name": "ChanCo", "channels": [
        {"platform": "youtube", "handle": "@chan", "url": "https://youtube.com/@chan", "follower_count": 500}]}).json()
    cid = a["channels"][0]["id"]
    got = client.patch(f"/api/channels/{cid}", json={"follower_count": 900}).json()["channels"][0]
    assert got["platform"] == "youtube" and got["handle"] == "@chan" and got["follower_count"] == 900
