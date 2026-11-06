"""Direct checkout sync (read-only): pull a product's orders from Stripe or Gumroad instead of a CSV export.

- Stripe: a *restricted* key with read access to Checkout Sessions, Payment Intents, Charges and Balance
  transactions. The product's sync ref is its Payment Link ID (plink_…). Fees come from the balance transaction;
  the channel comes from client_reference_id (add ?client_reference_id=<channel> to the Payment Link URL) or
  metadata.utm_source.
- Gumroad: an access token from Settings → Advanced → Applications. The sync ref is the Gumroad product ID.

Keys are kept in the macOS Keychain and only ever sent to the provider's own API host. Re-syncing is safe:
orders are matched on their provider ID, and refunds/fees on already-imported orders are updated.
"""
from datetime import datetime, timezone

import httpx

from .. import db, settings_store

STRIPE_API = "https://api.stripe.com/v1"
GUMROAD_API = "https://api.gumroad.com/v2"
MAX_PAGES = 50
_transport: httpx.BaseTransport | None = None  # tests inject a MockTransport


class SyncError(Exception):
    pass


def _client(**kw) -> httpx.Client:
    return httpx.Client(timeout=30, transport=_transport, **kw)


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None


def stripe_orders(key: str, payment_link: str) -> list[dict]:
    out, after = [], None
    with _client(auth=(key, "")) as c:
        for _ in range(MAX_PAGES):
            params = [("payment_link", payment_link), ("status", "complete"), ("limit", "100"),
                      ("expand[]", "data.payment_intent.latest_charge.balance_transaction")]
            if after:
                params.append(("starting_after", after))
            r = c.get(f"{STRIPE_API}/checkout/sessions", params=params)
            if r.status_code in (401, 403):
                raise SyncError("Stripe rejected the key. Use a restricted key with read access to Checkout Sessions, "
                                "Payment Intents, Charges and Balance transactions.")
            if r.status_code == 404 or (r.status_code == 400 and "payment_link" in r.text):
                raise SyncError(f"Stripe doesn't recognise the Payment Link ID '{payment_link}'. It starts with plink_.")
            if r.status_code >= 400:
                raise SyncError(f"Stripe error {r.status_code}: {r.json().get('error', {}).get('message', '')[:200]}")
            body = r.json()
            for s in body.get("data", []):
                if s.get("payment_status") not in ("paid", "no_payment_required"):
                    continue
                pi = s.get("payment_intent") if isinstance(s.get("payment_intent"), dict) else {}
                ch = pi.get("latest_charge") if isinstance(pi.get("latest_charge"), dict) else {}
                bt = ch.get("balance_transaction") if isinstance(ch.get("balance_transaction"), dict) else {}
                fee = bt.get("fee")
                out.append({"order_ref": s["id"], "date": _iso(s.get("created")),
                            "amount": round((s.get("amount_total") or 0) / 100, 2),
                            "refunded_amount": round((ch.get("amount_refunded") or 0) / 100, 2),
                            "fee": round(fee / 100, 2) if fee is not None else None,
                            "channel": (s.get("client_reference_id") or (s.get("metadata") or {}).get("utm_source") or None),
                            "currency": s.get("currency")})
            if not body.get("has_more") or not body.get("data"):
                break
            after = body["data"][-1]["id"]
    return out


def gumroad_orders(token: str, product_id: str) -> list[dict]:
    out, page_key = [], None
    with _client(headers={"Authorization": f"Bearer {token}"}) as c:
        for _ in range(MAX_PAGES):
            params = {"product_id": product_id}
            if page_key:
                params["page_key"] = page_key
            r = c.get(f"{GUMROAD_API}/sales", params=params)
            if r.status_code in (401, 403):
                raise SyncError("Gumroad rejected the access token. Create one in Gumroad → Settings → Advanced → Applications.")
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code >= 400 or not body.get("success", False):
                raise SyncError(f"Gumroad error {r.status_code}: {str(body.get('message', ''))[:200]}")
            for s in body.get("sales", []):
                price = (s.get("price") or 0) / 100
                fee = s.get("gumroad_fee")
                out.append({"order_ref": str(s["id"]), "date": (s.get("created_at") or "")[:10] or None,
                            "amount": round(price, 2), "refunded_amount": round(price, 2) if s.get("refunded") else 0.0,
                            "fee": round(fee / 100, 2) if fee is not None else None,
                            "channel": (s.get("referrer") or None), "currency": s.get("currency")})
            page_key = body.get("next_page_key")
            if not page_key:
                break
    return out


PROVIDERS = {"stripe": ("stripe_api_key", stripe_orders), "gumroad": ("gumroad_access_token", gumroad_orders)}


def sync_product(pid: str) -> dict:
    p = db.one("SELECT * FROM products WHERE id=?", (pid,))
    if not p or not p.get("sync_provider") or not p.get("sync_ref"):
        raise SyncError("Choose a checkout provider and enter the product's ID on that checkout first.")
    secret, fetch = PROVIDERS[p["sync_provider"]]
    key = settings_store.get_secret(secret)
    if not key:
        raise SyncError(f"Add your {'Stripe restricted key' if p['sync_provider'] == 'stripe' else 'Gumroad access token'} in Settings first.")
    try:
        orders = fetch(key, p["sync_ref"].strip())
    except httpx.HTTPError as e:
        raise SyncError(f"Couldn't reach {p['sync_provider'].title()}: {type(e).__name__}") from None
    currencies = {o["currency"] for o in orders if o.get("currency")} - {"usd"}
    new = updated = 0
    with db.tx() as c:
        for o in orders:
            cur = c.execute("INSERT OR IGNORE INTO product_sales (id, product_id, order_ref, date, amount, refunded_amount, fee, "
                            "channel, origin, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (db.new_id("ps"), pid, o["order_ref"], o["date"], o["amount"], o["refunded_amount"], o["fee"],
                             (o["channel"] or None) and str(o["channel"])[:80], p["sync_provider"], db.now()))
            if cur.rowcount:
                new += 1
                continue
            cur = c.execute("UPDATE product_sales SET refunded_amount=?, fee=COALESCE(?, fee) WHERE product_id=? AND order_ref=? "
                            "AND (refunded_amount != ? OR (fee IS NULL AND ? IS NOT NULL))",
                            (o["refunded_amount"], o["fee"], pid, o["order_ref"], o["refunded_amount"], o["fee"]))
            updated += cur.rowcount
        result = {"provider": p["sync_provider"], "fetched": len(orders), "new": new, "updated": updated, "at": db.now(),
                  "warnings": [f"Some orders are in {', '.join(sorted(currencies)).upper()}; amounts are stored as-is, not converted."]
                  if currencies else []}
        db.update(c, "products", pid, {"last_synced_at": result["at"], "last_sync_json": result, "updated_at": db.now()})
        db.log_activity(c, p["audience_id"], "sales", f"Synced {new} new orders from {p['sync_provider'].title()} for '{p['name']}'")
    return result
