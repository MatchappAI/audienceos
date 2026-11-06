import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { del, patch, post } from "../api";
import { date, money, today } from "../format";
import { Demo, Empty, ErrorBox, Loading, Stat, Status, useApi, useAsync, useToast, V } from "../components/ui";

export function ProductList({ audienceId }: { audienceId?: string }) {
  const { data, error, loading, reload } = useApi<any[]>(`/api/products${audienceId ? `?audience_id=${audienceId}` : ""}`);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return <div className="card"><Empty title="No products yet">Create a product from a validated opportunity. Products are sold through your own external checkout; AudienceOS tracks approval, launch, sales and costs.</Empty></div>;
  return (
    <div className="card" style={{ padding: 0 }}>
      <table className="t">
        <thead><tr><th style={{ paddingLeft: 20 }}>Product</th><th>Status</th><th className="num">Price</th><th className="num">Orders</th>
          <th className="num">Net sales</th><th className="num">Contribution</th><th className="num">Margin</th></tr></thead>
        <tbody>{data.map((p) => (
          <tr key={p.id}>
            <td style={{ paddingLeft: 20 }}><div className="row" style={{ gap: 6 }}><Link className="strong" to={`/products/${p.id}`}>{p.name}</Link><Demo on={p.is_demo} /></div>
              <div className="small muted">{p.org_name}{p.storefront ? ` · ${p.storefront}` : ""}</div></td>
            <td>{p.reapproval ? <span className="badge warn" title={p.reapproval.message}>Back to draft</span> : <Status s={p.status} />}{p.reapproval && <div className="tiny faint">re-approve to relaunch</div>}</td>
            <td className="num">{money(p.price)}<div className="tiny faint">{p.price_model}</div></td>
            <td className="num">{p.pnl.orders}</td>
            <td className="num">{money(p.pnl.net_sales)}</td>
            <td className="num">{money(p.pnl.contribution)}</td>
            <td className="num"><V v={p.pnl.margin_pct} kind="pct" digits={1} /></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function Creators() {
  const { data, error, loading, reload } = useApi<any>("/api/creators");
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Creators & Revenue</h1>
          <div className="sub">Agency view: where each creator is in the pipeline, their revenue-share deal, and what they're owed.</div>
        </div>
        <Link className="btn primary" to="/audiences?new=1">Add creator</Link>
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.creators.length === 0 && <div className="card"><Empty title="No creators yet" actions={<Link className="btn primary" to="/audiences?new=1">Add a creator</Link>} /></div>}
      {data && data.creators.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="t">
            <thead><tr><th style={{ paddingLeft: 20 }}>Creator</th><th style={{ width: 240 }}>Pipeline stage</th><th>Deal</th>
              <th className="num">Net sales</th><th className="num">Creator share</th><th className="num">Agency share</th><th className="num">Balance owed</th></tr></thead>
            <tbody>{data.creators.map((c: any) => {
              const idx = data.stages.findIndex((s: any) => s.key === c.stage);
              return (
                <tr key={c.id}>
                  <td style={{ paddingLeft: 20 }}><div className="row" style={{ gap: 6 }}><Link className="strong" to={`/creators/${c.id}`}>{c.name}</Link><Demo on={c.is_demo} /></div>
                    <div className="small muted">{c.kind}{c.contact_name ? ` · ${c.contact_name}` : ""}</div></td>
                  <td><div className="small mb" style={{ marginBottom: 4 }}>{c.stage_label}</div>
                    <div className="pipeline" title={data.stages.map((s: any) => s.label).join(" → ")}>{data.stages.map((s: any, i: number) => <div key={s.key} className={i <= idx ? "on" : ""} />)}</div></td>
                  <td className="small">{c.deal ? `${c.deal.creator_share_pct}% creator / ${100 - c.deal.creator_share_pct}% agency` : <span className="badge warn">no deal</span>}
                    {c.deal && <div className="tiny faint">of {c.deal.basis === "contribution" ? "contribution" : "net sales after fees"}</div>}</td>
                  <td className="num">{money(c.totals.net_sales)}</td>
                  <td className="num">{c.deal ? money(c.totals.creator_share) : "—"}</td>
                  <td className="num">{c.deal ? money(c.totals.agency_share) : "—"}</td>
                  <td className="num strong">{c.balance_owed == null ? "—" : money(c.balance_owed)}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}
      <PayoutsDue />
      <p className="small muted mt">Stages: {data?.stages.map((s: any) => s.label).join(" → ")}. Each stage is derived from stored data (sources, opportunities, experiments, products, sales).</p>
    </div>
  );
}

function PayoutsDue() {
  const { data } = useApi<any>("/api/payouts/due");
  if (!data || data.rows.length === 0) return null;
  return (
    <div className="card mt2">
      <div className="card-head"><h2>Payouts due · {money(data.total)}</h2><a className="btn primary sm" href="/api/payouts/export.csv">Download payout file</a></div>
      <table className="t small"><tbody>{data.rows.map((r: any) => (
        <tr key={r.organization_id}><td><Link to={`/creators/${r.organization_id}`}>{r.creator}</Link></td><td className="muted">{r.recipientEmail || <span className="badge warn">no email</span>}</td><td className="num strong">{money(Number(r.amount))}</td></tr>))}</tbody></table>
      <p className="tiny faint mt">CSV in Wise batch-payment format (works as a plain list for any bank). After you pay, record each payout on the creator's page. Demo creators are excluded.</p>
    </div>
  );
}

function DealCard({ st, orgId, reload }: { st: any; orgId: string; reload: () => void }) {
  const d = st.deal;
  const [edit, setEdit] = useState(!d);
  const [f, setF] = useState<any>({ creator_share_pct: d?.creator_share_pct ?? 70, basis: d?.basis ?? "contribution", start_date: d?.start_date ?? "", end_date: d?.end_date ?? "", notes: d?.notes ?? "",
    loss_carry_forward: !!d?.loss_carry_forward, min_guarantee_monthly: d?.min_guarantee_monthly ?? "", guarantee_months: d?.guarantee_months ?? "" });
  const act = useAsync();
  const save = async () => {
    if (await act.run(() => post(`/api/creators/${orgId}/deal`, { ...f, creator_share_pct: Number(f.creator_share_pct), start_date: f.start_date || null, end_date: f.end_date || null, notes: f.notes || null,
      min_guarantee_monthly: f.min_guarantee_monthly === "" ? null : Number(f.min_guarantee_monthly), guarantee_months: f.guarantee_months === "" ? null : Number(f.guarantee_months) }))) { setEdit(false); reload(); }
  };
  return (
    <div className="card">
      <div className="card-head"><h2>Revenue-share deal</h2>{!edit && <button className="btn sm" onClick={() => setEdit(true)}>Change terms</button>}</div>
      {!edit && d ? (
        <dl className="kv small">
          <dt>Split</dt><dd><b>{d.creator_share_pct}%</b> to creator · <b>{100 - d.creator_share_pct}%</b> to agency</dd>
          <dt>Split base</dt><dd>{d.basis === "contribution" ? "Contribution — net sales minus payment fees minus shared costs" : "Net sales minus payment fees"}</dd>
          <dt>Losses</dt><dd>{d.loss_carry_forward ? "Carry forward — offset against later profit across all products" : "Not charged to the creator (each product floored at $0)"}</dd>
          <dt>Minimum</dt><dd>{d.min_guarantee_monthly ? `${money(d.min_guarantee_monthly)}/month, recoupable${d.guarantee_months ? `, for ${d.guarantee_months} months` : ""}` : "None"}</dd>
          <dt>Term</dt><dd>{!d.start_date && !d.end_date ? "Open-ended" : `${d.start_date ? date(d.start_date) : "—"} to ${d.end_date ? date(d.end_date) : "open-ended"}`}</dd>
          <dt>Notes</dt><dd>{d.notes || "—"}</dd>
        </dl>
      ) : (
        <>
          <div className="grid g2">
            <label className="field"><span>Creator share (%)</span><input type="number" min={0} max={100} value={f.creator_share_pct} onChange={(e) => setF({ ...f, creator_share_pct: e.target.value as any })} /></label>
            <label className="field"><span>Split base</span>
              <select value={f.basis} onChange={(e) => setF({ ...f, basis: e.target.value })}>
                <option value="contribution">Contribution (after fees and shared costs)</option><option value="net_sales">Net sales after payment fees</option>
              </select></label>
            <label className="field"><span>Start</span><input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></label>
            <label className="field"><span>End</span><input type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} /></label>
          </div>
          <label className="check small"><input type="checkbox" checked={f.loss_carry_forward} onChange={(e) => setF({ ...f, loss_carry_forward: e.target.checked })} />
            <span>Carry losses forward — a loss on one product or month is offset against later profit before the creator's share</span></label>
          <div className="grid g2">
            <label className="field"><span>Minimum guarantee ($/month)</span><input type="number" min={0} step="0.01" value={f.min_guarantee_monthly} placeholder="none" onChange={(e) => setF({ ...f, min_guarantee_monthly: e.target.value })} /></label>
            <label className="field"><span>Guaranteed months</span><input type="number" min={1} value={f.guarantee_months} placeholder="open-ended" onChange={(e) => setF({ ...f, guarantee_months: e.target.value })} /></label>
          </div>
          {f.min_guarantee_monthly !== "" && Number(f.min_guarantee_monthly) > 0 && <p className="tiny faint">Recoupable: for each completed month from the start date, the creator is owed at least this much in total; their earned share pays it back first.</p>}
          <label className="field"><span>Notes</span><input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="e.g. signed agreement dated…" /></label>
          <p className="small muted">Agency share = {100 - Number(f.creator_share_pct || 0)}%. Changing terms ends the current deal and starts a new one; it applies to all-time figures in statements.</p>
          <div className="row"><button className="btn primary" onClick={save} disabled={act.busy}>Save deal</button>{d && <button className="btn" onClick={() => setEdit(false)}>Cancel</button>}</div>
        </>
      )}
      <ErrorBox error={act.error} />
    </div>
  );
}

export function CreatorDetail() {
  const { id = "" } = useParams();
  const [period, setPeriod] = useState({ start: "", end: "" });
  const qs = new URLSearchParams();
  if (period.start) qs.set("start", period.start);
  if (period.end) qs.set("end", period.end);
  const { data: st, error, loading, reload } = useApi<any>(`/api/creators/${id}/statement?${qs}`);
  const { data: auds } = useApi<any[]>("/api/audiences");
  const [po, setPo] = useState({ date: today(), amount: "", reference: "", note: "" });
  const [contact, setContact] = useState<any>(null);
  const act = useAsync();
  const toast = useToast();
  if (loading && !st) return <div className="page"><Loading /></div>;
  if (error || !st) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  const org = st.organization;
  const t = st.totals;
  const myAuds = (auds || []).filter((a) => a.organization_id === org.id);
  const addPayout = async () => {
    if (await act.run(() => post(`/api/creators/${id}/payouts`, { ...po, amount: Number(po.amount), reference: po.reference || null, note: po.note || null }))) {
      setPo({ ...po, amount: "", reference: "", note: "" }); toast("Payout recorded"); reload();
    }
  };
  const saveContact = async () => { if (await act.run(() => patch(`/api/creators/${id}`, contact))) { setContact(null); reload(); } };
  return (
    <div className="page">
      <div className="crumbs"><Link to="/creators">Creators & Revenue</Link></div>
      <div className="page-head">
        <div>
          <div className="row" style={{ gap: 8 }}><h1>{org.name}</h1><Demo on={org.is_demo} /></div>
          <div className="sub">{org.contact_name || "No contact"}{org.contact_email ? ` · ${org.contact_email}` : ""} <button className="linkbtn small" onClick={() => setContact({ contact_name: org.contact_name || "", contact_email: org.contact_email || "" })}>edit</button></div>
        </div>
        <div className="row">{myAuds.map((a) => <Link key={a.id} className="btn sm" to={`/audiences/${a.id}`}>{a.name}</Link>)}
          <a className="btn sm" href={`/api/creators/${id}/portal`} target="_blank" rel="noreferrer" title="Read-only page for the creator: earnings, products, channels, payouts">Creator view ↗</a>
          <a className="btn sm" href={`/api/creators/${id}/portal?download=true`} title="Download the creator view as one HTML file to send them">Download for creator</a></div>
      </div>
      {contact && (
        <div className="card mb row">
          <input placeholder="Contact name" value={contact.contact_name} onChange={(e) => setContact({ ...contact, contact_name: e.target.value })} style={{ maxWidth: 240 }} />
          <input placeholder="Email" value={contact.contact_email} onChange={(e) => setContact({ ...contact, contact_email: e.target.value })} style={{ maxWidth: 280 }} />
          <button className="btn primary sm" onClick={saveContact}>Save</button><button className="btn sm" onClick={() => setContact(null)}>Cancel</button>
        </div>
      )}
      {st.warnings.map((w: string) => <div key={w} className="notice warn small mb">{w}</div>)}
      {st.entitlement?.loss_carried_forward > 0 && <div className="notice small mb">A loss of <b>{money(st.entitlement.loss_carried_forward)}</b> is carried forward; it's offset against future profit before the creator's share.</div>}
      <div className="grid g4">
        <Stat label="Net sales (period)" value={money(t.net_sales)} hint={`${t.orders} orders · ${money(t.refunds)} refunded`} />
        <Stat label="Creator share (period)" value={st.deal ? money(t.creator_share) : "—"} hint={st.deal ? `${st.deal.creator_share_pct}% of split base ${money(t.split_base)}` : "set a deal"} />
        <Stat label="Agency share (period)" value={st.deal ? money(t.agency_share) : "—"} hint={st.deal ? `${money(t.agency_net_after_own_costs)} after agency-only costs` : "set a deal"} />
        <Stat label="Balance owed to creator" value={st.balance_owed == null ? "—" : money(st.balance_owed)} hint={st.deal ? `entitled ${money(st.all_time_creator_share)}${st.entitlement?.guarantee_top_up ? ` (incl. ${money(st.entitlement.guarantee_top_up)} guarantee)` : ""} − paid ${money(st.paid_out)}` : "set a deal"} />
      </div>
      <div className="grid g-side mt2">
        <div className="stack">
          <div className="card">
            <div className="card-head"><h2>Statement</h2>
              <div className="row small">
                <input type="date" value={period.start} onChange={(e) => setPeriod({ ...period, start: e.target.value })} style={{ width: 150 }} aria-label="From" /> to
                <input type="date" value={period.end} onChange={(e) => setPeriod({ ...period, end: e.target.value })} style={{ width: 150 }} aria-label="To" />
                {(period.start || period.end) && <button className="btn ghost sm" onClick={() => setPeriod({ start: "", end: "" })}>All time</button>}
                <a className="btn sm" href={`/api/creators/${id}/statement.csv?${qs}`}>CSV</a>
                <a className="btn sm" href={`/api/creators/${id}/statement.pdf?${qs}`}>PDF</a>
              </div></div>
            {st.lines.length === 0 ? <Empty title="No products yet">Products created from this creator's opportunities appear here with their sales and costs.</Empty> : (
              <div className="table-wrap">
                <table className="t small">
                  <thead><tr><th>Product</th><th className="num">Orders</th><th className="num">Gross</th><th className="num">Refunds</th><th className="num">Fees</th>
                    <th className="num">Shared costs</th><th className="num">Split base</th><th className="num">Creator</th><th className="num">Agency</th></tr></thead>
                  <tbody>
                    {st.lines.map((l: any) => (
                      <tr key={l.product_id}><td><Link to={`/products/${l.product_id}`}>{l.product}</Link> {l.status === "draft" && (l.launched_at || l.orders > 0) ? <span className="badge warn" title="Price, name or checkout link changed after approval — re-approve to relaunch. Sales are kept.">Back to draft</span> : <Status s={l.status} />}{l.fees_missing ? <div className="tiny" style={{ color: "var(--warn)" }}>{l.fees_missing} orders without fee data</div> : null}</td>
                        <td className="num">{l.orders}</td><td className="num">{money(l.gross)}</td><td className="num">{money(l.refunds)}</td><td className="num">{money(l.fees)}</td>
                        <td className="num">{money(l.shared_costs)}</td><td className="num">{money(l.split_base)}</td>
                        <td className="num strong">{l.creator_share == null ? "—" : money(l.creator_share)}</td><td className="num">{l.agency_share == null ? "—" : money(l.agency_share)}</td></tr>
                    ))}
                    <tr><td className="strong">Total</td><td className="num">{t.orders}</td><td className="num">{money(t.gross)}</td><td className="num">{money(t.refunds)}</td><td className="num">{money(t.fees)}</td>
                      <td className="num">{money(t.shared_costs)}</td><td className="num">{money(t.split_base)}</td><td className="num strong">{st.deal ? money(t.creator_share) : "—"}</td><td className="num">{st.deal ? money(t.agency_share) : "—"}</td></tr>
                  </tbody>
                </table>
              </div>
            )}
            <details className="fold mt"><summary>How these numbers are calculated</summary><pre className="small prewrap" style={{ fontFamily: "inherit" }}>{st.definitions}</pre></details>
          </div>
        </div>
        <div className="stack">
          <DealCard st={st} orgId={id} reload={reload} />
          <div className="card">
            <h2>Payouts to creator</h2>
            <div className="grid g2" style={{ gap: 8 }}>
              <input type="date" value={po.date} onChange={(e) => setPo({ ...po, date: e.target.value })} aria-label="Date" />
              <input type="number" min="0" step="0.01" placeholder="Amount $" value={po.amount} onChange={(e) => setPo({ ...po, amount: e.target.value })} aria-label="Amount" />
              <input placeholder="Reference / transfer ID" value={po.reference} onChange={(e) => setPo({ ...po, reference: e.target.value })} aria-label="Reference" />
              <button className="btn primary" onClick={addPayout} disabled={act.busy || !po.amount}>Record payout</button>
            </div>
            <p className="tiny faint mt">Record payments you've actually made. AudienceOS doesn't move money.</p>
            <ErrorBox error={act.error} />
            {st.payouts.length > 0 && (
              <table className="t small mt"><tbody>{st.payouts.map((p: any) => (
                <tr key={p.id}><td className="nowrap">{date(p.date)}</td><td className="num">{money(p.amount)}</td><td className="muted" style={{ wordBreak: "break-word" }}>{p.reference || ""}</td>
                  <td><button className="btn ghost sm" onClick={async () => { if (window.confirm("Delete this payout record?") && (await act.run(() => del(`/api/payouts/${p.id}`)))) reload(); }}>✕</button></td></tr>
              ))}</tbody></table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
