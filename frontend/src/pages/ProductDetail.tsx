import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { del, patch, post, upload } from "../api";
import { date, dateTime, money, today } from "../format";
import { Demo, ErrorBox, Loading, Stat, Status, useApi, useAsync, useToast, V } from "../components/ui";

function Setup({ p, reload }: { p: any; reload: () => void }) {
  const [f, setF] = useState<any>({});
  useEffect(() => setF({ name: p.name, price: p.price ?? "", price_model: p.price_model, storefront: p.storefront || "", checkout_url: p.checkout_url || "", notes: p.notes || "" }), [p.id, p.updated_at]);
  const act = useAsync();
  const toast = useToast();
  const save = async () => {
    const body = { ...f, price: f.price === "" ? null : Number(f.price), checkout_url: f.checkout_url || null, storefront: f.storefront || null };
    const r = await act.run(() => patch(`/api/products/${p.id}`, body));
    if (r) { toast(r.status === "draft" && p.status !== "draft" ? "Saved — changes need re-approval" : "Saved"); reload(); }
  };
  const pause = async (s: string) => { if (await act.run(() => patch(`/api/products/${p.id}`, { status: s }))) reload(); };
  return (
    <div className="card">
      <div className="card-head"><h2>Product & storefront</h2>
        <div className="row">{p.status === "launched" && <button className="btn sm" onClick={() => pause("paused")}>Pause</button>}
          {p.status !== "retired" && <button className="btn ghost sm" onClick={() => pause("retired")}>Retire</button>}</div></div>
      <div>
        <label className="field"><span>Name</span><input value={f.name ?? ""} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <div className="grid" style={{ gap: 10, gridTemplateColumns: "1fr 1.3fr" }}>
          <label className="field"><span>Price ($)</span><input type="number" min="0" step="0.01" value={f.price ?? ""} onChange={(e) => setF({ ...f, price: e.target.value })} /></label>
          <label className="field"><span>Pricing</span><select value={f.price_model || "one-time"} onChange={(e) => setF({ ...f, price_model: e.target.value })}>
            {["one-time", "monthly", "annual", "per-session"].map((m) => <option key={m}>{m}</option>)}</select></label>
        </div>
        <label className="field"><span>Storefront</span><input value={f.storefront ?? ""} placeholder="Gumroad, Stripe Payment Link, Shopify…" onChange={(e) => setF({ ...f, storefront: e.target.value })} /></label>
        <label className="field"><span>Checkout link (https)</span><input type="url" value={f.checkout_url ?? ""} placeholder="https://…" onChange={(e) => setF({ ...f, checkout_url: e.target.value })} /></label>
      </div>
      <label className="field"><span>Notes</span><textarea rows={2} value={f.notes ?? ""} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
      <p className="small muted">Changing the name, price or checkout link of an approved product sends it back for approval.</p>
      <ErrorBox error={act.error} />
      <button className="btn primary" onClick={save} disabled={act.busy}>Save</button>
    </div>
  );
}

function Launch({ p, reload }: { p: any; reload: () => void }) {
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [approver, setApprover] = useState("");
  const [note, setNote] = useState("");
  const act = useAsync();
  useEffect(() => setChecks(Object.fromEntries(p.checklist.map((c: any) => [c.key, c.done]))), [p.id, p.updated_at]);
  const approve = async () => { if (await act.run(() => post(`/api/products/${p.id}/approve`, { checklist: checks, approver, note: note || null }))) reload(); };
  const launch = async () => { if (await act.run(() => post(`/api/products/${p.id}/launch`))) reload(); };
  const ap = p.approval || {};
  return (
    <div className="card">
      <h2>Launch approval</h2>
      {p.asset_warnings?.length > 0 && <div className="notice warn small mb">{p.asset_warnings.map((w: any) => (
        <div key={w.asset_id}><b>{w.title}</b> mentions {w.amounts.join(", ")}, but this product sells at {money(p.price)}. If that's the price, edit the draft.</div>))}</div>}
      {p.status === "draft" && (
        <>
          {p.reapproval && <div className="notice warn small mb"><b>Needs re-approval.</b> This product was {p.reapproval.from_status}{p.reapproval.previous_approver ? ` (approved by ${p.reapproval.previous_approver})` : ""}; its {p.reapproval.fields.length ? p.reapproval.fields.join(", ") : "price, name or checkout link"} changed{p.reapproval.at ? ` on ${dateTime(p.reapproval.at)}` : ""}, so what buyers see must be signed off again.</div>}
          <p className="small muted">Nothing goes live without a human sign-off. Confirm each check, then approve.</p>
          {p.checklist.map((c: any) => (
            <label key={c.key} className="check small"><input type="checkbox" checked={!!checks[c.key]} onChange={(e) => setChecks({ ...checks, [c.key]: e.target.checked })} /><span>{c.label}</span></label>
          ))}
          {p.assets.length > 0 && <div className="small mt">Assets: {p.assets.map((a: any) => <span key={a.id} style={{ marginRight: 8 }}>{a.title} <Status s={a.status} /></span>)}</div>}
          <label className="field mt"><span>Approved by</span><input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your name" /></label>
          <label className="field"><span>Note</span><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" /></label>
          <button className="btn primary" onClick={approve} disabled={act.busy || !approver.trim()}>Approve for launch</button>
        </>
      )}
      {p.status !== "draft" && (
        <>
          <div className="notice good small">Approved by <b>{ap.approver}</b> on {dateTime(ap.at || p.approved_at)}{ap.note ? ` — ${ap.note}` : ""}</div>
          {p.status === "approved" && (
            <div className="mt"><p className="small">Mark as launched after you publish it on your storefront.</p>
              <button className="btn accent" onClick={launch} disabled={act.busy}>Mark as launched</button></div>
          )}
          {p.status === "paused" && <button className="btn mt" onClick={launch} disabled={act.busy}>Resume (mark launched)</button>}
          {p.launched_at && <p className="small muted mt">Launched {date(p.launched_at)}.</p>}
        </>
      )}
      <ErrorBox error={act.error} />
    </div>
  );
}

function Sales({ p, reload }: { p: any; reload: () => void }) {
  const blank = { order_ref: "", date: today(), amount: "", refunded_amount: "", fee: "", channel: "" };
  const [f, setF] = useState<any>(blank);
  const [imp, setImp] = useState<any>(null);
  const file = useRef<HTMLInputElement>(null);
  const act = useAsync();
  const add = async () => {
    const body = { order_ref: f.order_ref, date: f.date || null, amount: Number(f.amount), refunded_amount: Number(f.refunded_amount || 0), fee: f.fee === "" ? null : Number(f.fee), channel: f.channel || null };
    if (await act.run(() => post(`/api/products/${p.id}/sales`, body))) { setF(blank); reload(); }
  };
  const doImport = async (fl: File) => {
    const fd = new FormData(); fd.append("file", fl);
    const r = await act.run(() => upload(`/api/products/${p.id}/sales/import`, fd));
    if (r) { setImp(r.result); reload(); }
  };
  return (
    <div className="card">
      <div className="card-head"><h2>Sales</h2>
        <button className="btn sm" onClick={() => file.current?.click()}>Import orders CSV</button>
        <input ref={file} type="file" accept=".csv,text/csv" hidden onChange={(e) => { const fl = e.target.files?.[0]; if (fl) doImport(fl); e.target.value = ""; }} /></div>
      <p className="small muted">Export orders from your checkout (Stripe, Gumroad, Shopify…). Needs an order ID and amount; refund, fee, date and utm_source/channel columns are picked up when present. Re-importing skips orders already recorded.</p>
      {imp && <div className={`notice ${imp.errors?.length ? "warn" : "good"} small mb`}>Imported {imp.imported} orders{imp.skipped_duplicates ? `, skipped ${imp.skipped_duplicates} duplicates` : ""}.
        {imp.errors?.length ? <ul className="bul">{imp.errors.map((e: string) => <li key={e}>{e}</li>)}</ul> : null}</div>}
      <div className="grid" style={{ gridTemplateColumns: "1.1fr 1.25fr 0.9fr 0.9fr 0.8fr 1fr auto", gap: 8 }}>
        <input placeholder="Order ID" value={f.order_ref} onChange={(e) => setF({ ...f, order_ref: e.target.value })} aria-label="Order ID" />
        <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} aria-label="Date" />
        <input type="number" min="0" step="0.01" placeholder="Amount $" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} aria-label="Amount" />
        <input type="number" min="0" step="0.01" placeholder="Refund $" value={f.refunded_amount} onChange={(e) => setF({ ...f, refunded_amount: e.target.value })} aria-label="Refunded" />
        <input type="number" min="0" step="0.01" placeholder="Fee $" value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} aria-label="Fee" />
        <input placeholder="Channel" value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} aria-label="Channel" />
        <button className="btn" onClick={add} disabled={act.busy || !f.order_ref || f.amount === ""}>Add</button>
      </div>
      <ErrorBox error={act.error} />
      {p.sales.length > 0 && (
        <div className="table-wrap mt" style={{ maxHeight: 320, overflow: "auto" }}>
          <table className="t small">
            <thead><tr><th>Order</th><th>Date</th><th className="num">Amount</th><th className="num">Refunded</th><th className="num">Fee</th><th>Channel</th><th /></tr></thead>
            <tbody>{p.sales.map((s: any) => (
              <tr key={s.id}><td className="mono">{s.order_ref}</td><td>{date(s.date)}</td><td className="num">{money(s.amount)}</td>
                <td className="num">{s.refunded_amount ? money(s.refunded_amount) : "—"}</td><td className="num"><V v={s.fee} kind="usd" /></td>
                <td>{s.channel || <span className="faint">unattributed</span>}</td>
                <td><button className="btn ghost sm" onClick={async () => { if (await act.run(() => del(`/api/sales/${s.id}`))) reload(); }}>✕</button></td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Costs({ p, reload }: { p: any; reload: () => void }) {
  const blank = { date: today(), category: "production", amount: "", shared: true, note: "" };
  const [f, setF] = useState<any>(blank);
  const act = useAsync();
  const add = async () => { if (await act.run(() => post(`/api/products/${p.id}/costs`, { ...f, amount: Number(f.amount), note: f.note || null }))) { setF(blank); reload(); } };
  return (
    <div className="card">
      <h2>Costs</h2>
      <div className="grid" style={{ gridTemplateColumns: "1.25fr 1fr 0.9fr auto 1.3fr auto", gap: 8, alignItems: "center" }}>
        <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} aria-label="Date" />
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} aria-label="Category">
          {["production", "ads", "tools", "fulfillment", "contractor", "other"].map((c) => <option key={c}>{c}</option>)}</select>
        <input type="number" min="0" step="0.01" placeholder="Amount $" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} aria-label="Amount" />
        <label className="check small" style={{ margin: 0 }}><input type="checkbox" checked={f.shared} onChange={(e) => setF({ ...f, shared: e.target.checked })} /><span>Deduct before split</span></label>
        <input placeholder="Note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} aria-label="Note" />
        <button className="btn" onClick={add} disabled={act.busy || f.amount === ""}>Add</button>
      </div>
      <p className="tiny faint mt">“Deduct before split” costs reduce the split base when the deal uses contribution. Unticked costs are borne by the agency only.</p>
      <ErrorBox error={act.error} />
      {p.costs.length > 0 && (
        <table className="t small mt"><tbody>{p.costs.map((c: any) => (
          <tr key={c.id}><td className="nowrap">{date(c.date)}</td><td>{c.category}</td><td className="num">{money(c.amount)}</td><td>{c.shared ? <span className="badge">shared</span> : <span className="badge">agency only</span>}</td>
            <td className="muted">{c.note}</td><td><button className="btn ghost sm" onClick={async () => { if (await act.run(() => del(`/api/costs/${c.id}`))) reload(); }}>✕</button></td></tr>
        ))}</tbody></table>
      )}
    </div>
  );
}

export default function ProductDetail() {
  const { id = "" } = useParams();
  const { data: p, error, loading, reload } = useApi<any>(`/api/products/${id}`);
  if (loading) return <div className="page"><Loading /></div>;
  if (error || !p) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  const n = p.pnl;
  return (
    <div className="page">
      <div className="crumbs"><Link to={`/creators/${p.organization_id}`}>{p.org_name}</Link> / <Link to={`/audiences/${p.audience_id}/products`}>Products</Link></div>
      <div className="page-head">
        <div>
          <div className="row" style={{ gap: 8 }}><h1>{p.name}</h1>{p.reapproval ? <span className="badge warn" title={p.reapproval.message}>Back to draft</span> : <Status s={p.status} />}<Demo on={p.is_demo} /></div>
          <div className="sub">{money(p.price)} {p.price_model}{p.storefront ? ` · ${p.storefront}` : ""}{p.opportunity_id ? <> · from <Link to={`/opportunities/${p.opportunity_id}`}>opportunity</Link></> : null}
            {p.deal ? ` · creator ${p.deal.creator_share_pct}% / agency ${100 - p.deal.creator_share_pct}%` : " · no deal set"}</div>
        </div>
        {p.checkout_url && <a className="btn" href={p.checkout_url} target="_blank" rel="noreferrer noopener">Open checkout ↗</a>}
      </div>
      <div className="grid g4">
        <Stat label="Net sales" value={money(n.net_sales)} hint={`${n.orders} orders · ${money(n.gross)} gross − ${money(n.refunds)} refunds`} />
        <Stat label="Payment fees" value={money(n.fees)} hint={n.fees_missing ? `${n.fees_missing} orders missing fee data` : "from imported orders"} />
        <Stat label="Costs" value={money(n.shared_costs + n.agency_only_costs)} hint={`${money(n.shared_costs)} shared · ${money(n.agency_only_costs)} agency only`} />
        <Stat label="Contribution" value={money(n.contribution)} hint={<>margin <V v={n.margin_pct} kind="pct" digits={1} /></>} />
      </div>
      {p.reapproval && <div className="notice warn mt"><b>{p.reapproval.message}</b> The {n.orders} order{n.orders === 1 ? "" : "s"} below were recorded before the change and still count toward the statement.</div>}
      {n.fees_missing > 0 && <div className="notice warn small mt">{n.fees_missing} orders have no fee data; their fees count as $0. Import the fee column from your checkout export.</div>}
      <div className="grid g-side mt2">
        <div className="stack">
          <Sales p={p} reload={reload} />
          <Costs p={p} reload={reload} />
          {Object.keys(n.by_channel).length > 0 && (
            <div className="card"><h2>Sales by channel</h2>
              <table className="t small"><thead><tr><th>Channel</th><th className="num">Orders</th><th className="num">Net sales</th></tr></thead>
                <tbody>{Object.entries(n.by_channel).map(([k, v]: any) => <tr key={k}><td>{k}</td><td className="num">{v.orders}</td><td className="num">{money(v.net_sales)}</td></tr>)}</tbody></table>
              <p className="tiny faint mt">Attribution comes from the channel/utm_source column in your order export — it's only as good as your tracking links.</p></div>
          )}
        </div>
        <div className="stack">
          <Launch p={p} reload={reload} />
          <Setup p={p} reload={reload} />
        </div>
      </div>
    </div>
  );
}
