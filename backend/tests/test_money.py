"""Post-pilot money features: deal options, payout file, PDF statement, portal, next tests, checkout sync."""
import json
from datetime import date

import httpx

from app import settings_store
from app.services import agency, checkout_sync

FULL = {k: True for k, _ in agency.LAUNCH_CHECKLIST}


def _creator(client, name, price=40):
    a = client.post("/api/audiences", json={"org_name": name}).json()
    org = a["organization_id"]
    p = client.post("/api/products", json={"audience_id": a["id"], "name": f"{name} kit", "price": price,
                                           "checkout_url": "https://x.example/kit"}).json()
    client.post(f"/api/products/{p['id']}/approve", json={"checklist": FULL, "approver": "M"})
    client.post(f"/api/products/{p['id']}/launch")
    return a, org, p


def test_loss_carry_forward_offsets_profit(client):
    a, org, p1 = _creator(client, "CarryCo")
    p2 = client.post("/api/products", json={"audience_id": a["id"], "name": "Loser", "price": 10}).json()
    client.post(f"/api/products/{p1['id']}/sales", json={"order_ref": "a", "amount": 100, "fee": 0})
    client.post(f"/api/products/{p2['id']}/costs", json={"amount": 60, "shared": True})
    # Default: per-product floor — p1 earns 70, p2's loss isn't charged.
    st = client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "contribution"}).json()
    assert st["all_time_creator_share"] == 70.0 and st["entitlement"]["loss_carried_forward"] == 0
    # Carry forward: (100 − 60) × 70% = 28.
    st = client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "contribution",
                                                        "loss_carry_forward": True}).json()
    assert st["all_time_creator_share"] == 28.0
    assert st["totals"]["creator_share"] == 28.0
    assert any("carry-forward" in w for w in st["warnings"])
    # A deal-wide loss carries forward and nothing is owed.
    client.post(f"/api/products/{p2['id']}/costs", json={"amount": 100, "shared": True})
    st = client.get(f"/api/creators/{org}/statement").json()
    assert st["all_time_creator_share"] == 0 and st["entitlement"]["loss_carried_forward"] == 60.0


def test_minimum_guarantee_tops_up_and_recoups(client):
    a, org, p = _creator(client, "GuaranteeCo")
    st = client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "net_sales",
                                                        "start_date": "2026-07-15", "min_guarantee_monthly": 100,
                                                        "guarantee_months": 3}).json()
    deal = st["deal"]
    en = agency.entitlement_all_time(org, deal, today=date(2026, 9, 20))  # 2 completed months
    assert en["guarantee_months_completed"] == 2 and en["guarantee_top_up"] == 200 and en["entitlement"] == 200
    en = agency.entitlement_all_time(org, deal, today=date(2027, 6, 1))   # capped at 3 months
    assert en["guaranteed_to_date"] == 300
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "big", "amount": 1000, "fee": 0})
    en = agency.entitlement_all_time(org, deal, today=date(2027, 6, 1))   # earned 700 > 300: guarantee recouped
    assert en["earned"] == 700 and en["guarantee_top_up"] == 0 and en["entitlement"] == 700


def test_completed_months():
    assert agency.completed_months("2026-01-31", date(2026, 2, 28)) == 0
    assert agency.completed_months("2026-01-15", date(2026, 3, 15)) == 2
    assert agency.completed_months("bad", date(2026, 3, 15)) == 0


def test_payout_file_pdf_and_portal(client):
    a, org, p = _creator(client, "Payout <Co>")
    client.patch(f"/api/creators/{org}", json={"contact_name": "Pat Doe", "contact_email": "pat@example.com"})
    client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 70, "basis": "net_sales"})
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "x1", "amount": 50, "fee": 2, "channel": "newsletter"})
    due = client.get("/api/payouts/due").json()
    row = next(r for r in due["rows"] if r["organization_id"] == org)
    assert row["amount"] == "33.60" and row["recipientEmail"] == "pat@example.com"
    csv_text = client.get("/api/payouts/export.csv").text
    assert csv_text.splitlines()[0].startswith("name,recipientEmail,paymentReference") and "33.60" in csv_text
    pdf = client.get(f"/api/creators/{org}/statement.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    page = client.get(f"/api/creators/{org}/portal")
    assert page.status_code == 200 and "script-src" not in page.headers["content-security-policy"]
    assert "Payout &lt;Co&gt;" in page.text and "<script" not in page.text and "newsletter" in page.text
    assert "$33.60" in page.text  # balance owed
    # Fingerprint is stable for an unchanged statement and changes with the numbers.
    from app.services import statements
    f1 = statements.fingerprint(agency.statement(org))
    assert f1 == statements.fingerprint(agency.statement(org))
    client.post(f"/api/creators/{org}/payouts", json={"date": "2026-11-01", "amount": 10})
    assert statements.fingerprint(agency.statement(org)) != f1


def test_next_tests_suggestions(client):
    a, org, p = _creator(client, "OptCo", price=20)
    for i in range(6):
        client.post(f"/api/products/{p['id']}/sales", json={"order_ref": f"o{i}", "amount": 20, "fee": 1,
                                                           "channel": "instagram" if i < 5 else None})
    s = client.get(f"/api/products/{p['id']}/next-tests").json()["suggestions"]
    kinds = {x["kind"] for x in s}
    assert "price" in kinds and "channel" in kinds and "tracking" not in kinds
    price = next(x for x in s if x["kind"] == "price")
    assert price["experiment"]["price"] == 25.0  # low refunds → test +25%
    # A suggestion's prefill creates a valid experiment.
    x = client.post("/api/experiments", json=price["experiment"])
    assert x.status_code == 200 and x.json()["price"] == 25.0
    s = client.get(f"/api/products/{p['id']}/next-tests").json()
    assert 20.0 in s["prices_tested"] and 25.0 in s["prices_tested"]
    assert "price" not in {x["kind"] for x in s["suggestions"]}  # two prices now tried
    ov = client.get("/api/optimize").json()
    assert any(r["product_id"] == p["id"] and r["best_channel"] == "instagram" for r in ov["products"])


def _stripe_handler(req: httpx.Request):
    assert req.url.host == "api.stripe.com"
    page2 = req.url.params.get("starting_after") == "cs_2"
    data = [{"id": "cs_3", "created": 1762400000, "amount_total": 4000, "currency": "usd", "payment_status": "paid",
             "client_reference_id": None, "metadata": {"utm_source": "tiktok"},
             "payment_intent": {"latest_charge": {"amount_refunded": 4000, "balance_transaction": {"fee": 146}}}}] if page2 else [
            {"id": "cs_1", "created": 1762300000, "amount_total": 4000, "currency": "usd", "payment_status": "paid",
             "client_reference_id": "newsletter",
             "payment_intent": {"latest_charge": {"amount_refunded": 0, "balance_transaction": {"fee": 146}}}},
            {"id": "cs_unpaid", "created": 1762300000, "amount_total": 4000, "payment_status": "unpaid"},
            {"id": "cs_2", "created": 1762300500, "amount_total": 4000, "currency": "usd", "payment_status": "paid",
             "payment_intent": {"latest_charge": {"amount_refunded": 0, "balance_transaction": None}}}]
    return httpx.Response(200, json={"data": data, "has_more": not page2})


def test_stripe_sync_is_idempotent_and_updates_refunds(client, monkeypatch):
    a, org, p = _creator(client, "StripeCo")
    assert client.post(f"/api/products/{p['id']}/sync").status_code == 400  # not configured
    assert client.put(f"/api/products/{p['id']}/sync", json={"sync_provider": "stripe", "sync_ref": "buy.stripe.com/x"}).status_code == 400
    client.put(f"/api/products/{p['id']}/sync", json={"sync_provider": "stripe", "sync_ref": "plink_123"})
    r = client.post(f"/api/products/{p['id']}/sync")
    assert r.status_code == 400 and "Settings" in r.json()["detail"]  # no key
    settings_store.set_secret("stripe_api_key", "rk_test_fake")
    monkeypatch.setattr(checkout_sync, "_transport", httpx.MockTransport(_stripe_handler))
    try:
        res = client.post(f"/api/products/{p['id']}/sync").json()
        assert res["result"]["new"] == 3 and res["result"]["fetched"] == 3
        sales = {s["order_ref"]: s for s in res["product"]["sales"]}
        assert sales["cs_1"]["fee"] == 1.46 and sales["cs_1"]["channel"] == "newsletter" and sales["cs_1"]["origin"] == "stripe"
        assert sales["cs_3"]["refunded_amount"] == 40 and sales["cs_3"]["channel"] == "tiktok"
        assert sales["cs_2"]["fee"] is None
        again = client.post(f"/api/products/{p['id']}/sync").json()
        assert again["result"]["new"] == 0 and again["result"]["updated"] == 0
        assert again["product"]["last_sync"]["provider"] == "stripe"
    finally:
        settings_store.set_secret("stripe_api_key", None)


def test_gumroad_sync_and_auth_error(client, monkeypatch):
    a, org, p = _creator(client, "GumCo")
    client.put(f"/api/products/{p['id']}/sync", json={"sync_provider": "gumroad", "sync_ref": "prod_abc"})
    settings_store.set_secret("gumroad_access_token", "tok_fake")

    def ok(req):
        assert req.headers["authorization"] == "Bearer tok_fake" and req.url.params["product_id"] == "prod_abc"
        return httpx.Response(200, json={"success": True, "sales": [
            {"id": "g1", "created_at": "2026-11-02T10:00:00Z", "price": 2500, "gumroad_fee": 250, "refunded": False, "referrer": "youtube"},
            {"id": "g2", "created_at": "2026-11-03T10:00:00Z", "price": 2500, "gumroad_fee": 250, "refunded": True}]})
    try:
        monkeypatch.setattr(checkout_sync, "_transport", httpx.MockTransport(ok))
        res = client.post(f"/api/products/{p['id']}/sync").json()
        assert res["result"]["new"] == 2 and res["product"]["pnl"]["refunds"] == 25 and res["product"]["pnl"]["fees"] == 5
        monkeypatch.setattr(checkout_sync, "_transport", httpx.MockTransport(lambda r: httpx.Response(401, json={})))
        r = client.post(f"/api/products/{p['id']}/sync")
        assert r.status_code == 400 and "access token" in r.json()["detail"]
        assert "tok_fake" not in json.dumps(r.json())
    finally:
        settings_store.set_secret("gumroad_access_token", None)
