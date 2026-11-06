import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { del, patch, post, upload } from "../api";
import { date, money, num, pct } from "../format";
import { AssetPanel } from "../components/assets";
import { Demo, ErrorBox, Loading, Status, useApi, useAsync, useToast, V } from "../components/ui";
import { REC_TEXT } from "./Validation";

const OPS = [">=", "<=", ">", "<"];

function Setup({ x, reload }: { x: any; reload: () => void }) {
  const [f, setF] = useState<any>({});
  const [crit, setCrit] = useState<any[]>([]);
  useEffect(() => {
    setF({
      name: x.name || "", hypothesis: x.hypothesis || "", target_audience: x.target_audience || "", offer: x.offer || "",
      price: x.price ?? "", channel: x.channel || "", target_exposure: x.target_exposure ?? "", start_date: x.start_date || "",
      end_date: x.end_date || "", payment_fee_pct: x.payment_fee_pct ?? 0, payment_fee_fixed: x.payment_fee_fixed ?? 0,
      checkout_url: x.checkout_url || "", attribution_notes: x.attribution_notes || "", findings: x.findings || "",
      next_action: x.next_action || "", status: x.status,
    });
    setCrit((x.criteria || []).map((c: any) => ({ ...c })));
  }, [x.id, x.updated_at]);
  const act = useAsync();
  const toast = useToast();
  const n = (v: any) => (v === "" || v === null ? null : Number(v));
  const save = async () => {
    const body = { ...f, price: n(f.price), target_exposure: n(f.target_exposure), payment_fee_pct: n(f.payment_fee_pct) ?? 0,
      payment_fee_fixed: n(f.payment_fee_fixed) ?? 0, checkout_url: f.checkout_url || null, start_date: f.start_date || null, end_date: f.end_date || null,
      criteria: crit.filter((c) => c.metric && c.value !== "" && c.value !== null).map((c) => ({ metric: c.metric, op: c.op || ">=", value: Number(c.value) })) };
    if (await act.run(() => patch(`/api/experiments/${x.id}`, body))) { toast("Experiment saved"); reload(); }
  };
  const t = (k: string, label: string, type = "text", ph = "") => (
    <label className="field"><span>{label}</span><input type={type} value={f[k] ?? ""} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
  );
  return (
    <div className="card">
      <div className="card-head"><h2>Experiment design</h2>
        <select value={f.status || "draft"} onChange={(e) => setF({ ...f, status: e.target.value })} style={{ width: 150 }} aria-label="Status">
          <option value="draft">Draft</option><option value="running">Running</option><option value="completed">Completed</option>
        </select></div>
      {t("name", "Name")}
      <label className="field"><span>Hypothesis</span><textarea rows={2} value={f.hypothesis ?? ""} onChange={(e) => setF({ ...f, hypothesis: e.target.value })} /></label>
      <div className="grid g2">{t("target_audience", "Audience segment")}{t("offer", "Offer")}</div>
      <div className="grid g4">{t("price", "Price ($)", "number")}{t("channel", "Channel", "text", "e.g. newsletter, IG story")}{t("target_exposure", "Target landing visitors", "number")}
        {t("checkout_url", "Checkout link (https)", "url", "https://…")}</div>
      <div className="grid g4">{t("start_date", "Start", "date")}{t("end_date", "End", "date")}{t("payment_fee_pct", "Payment fee %", "number")}{t("payment_fee_fixed", "Fixed fee per sale $", "number")}</div>
      <h3 className="mt">Success criteria — decided before results come in</h3>
      {crit.length === 0 && <p className="small muted">Add at least one criterion, e.g. “Visitor → purchase ≥ 2%” and “Purchases ≥ 20”.</p>}
      {crit.map((c, i) => (
        <div key={i} className="grid" style={{ gridTemplateColumns: "1.6fr 70px 110px 30px", gap: 8, marginBottom: 6 }}>
          <select value={c.metric} onChange={(e) => setCrit(crit.map((d, j) => (j === i ? { ...d, metric: e.target.value } : d)))} aria-label="Metric">
            {x.metric_options.map((m: any) => <option key={m.key} value={m.key}>{m.label}{m.unit === "pct" ? " (%)" : m.unit === "usd" ? " ($)" : ""}</option>)}
          </select>
          <select value={c.op || ">="} onChange={(e) => setCrit(crit.map((d, j) => (j === i ? { ...d, op: e.target.value } : d)))} aria-label="Comparison">
            {OPS.map((o) => <option key={o} value={o}>{o}</option>)}</select>
          <input type="number" step="any" value={c.value ?? ""} placeholder="value" onChange={(e) => setCrit(crit.map((d, j) => (j === i ? { ...d, value: e.target.value } : d)))} aria-label="Threshold" />
          <button className="btn ghost sm" onClick={() => setCrit(crit.filter((_, j) => j !== i))} aria-label="Remove">✕</button>
        </div>
      ))}
      <button className="btn sm" onClick={() => setCrit([...crit, { metric: "purchase_conversion", op: ">=", value: "" }])}>+ Add criterion</button>
      <label className="field mt2"><span>Attribution notes & assumptions</span><textarea rows={2} value={f.attribution_notes ?? ""} onChange={(e) => setF({ ...f, attribution_notes: e.target.value })} placeholder="e.g. visits from UTM-tagged link only; story views counted as impressions" /></label>
      <div className="grid g2">
        <label className="field"><span>Findings</span><textarea rows={2} value={f.findings ?? ""} onChange={(e) => setF({ ...f, findings: e.target.value })} /></label>
        <label className="field"><span>Next action</span><textarea rows={2} value={f.next_action ?? ""} onChange={(e) => setF({ ...f, next_action: e.target.value })} /></label>
      </div>
      <ErrorBox error={act.error} />
      <button className="btn primary" onClick={save} disabled={act.busy}>Save design</button>
    </div>
  );
}

function Results({ x, reload }: { x: any; reload: () => void }) {
  const blank = { date: "", impressions: "", clicks: "", landing_visits: "", checkout_visits: "", purchases: "", gross_revenue: "", refunds: "", refund_amount: "", payment_fees: "", other_costs: "", note: "" };
  const [f, setF] = useState<any>(blank);
  const [imp, setImp] = useState<any>(null);
  const file = useRef<HTMLInputElement>(null);
  const act = useAsync();
  const add = async () => {
    const body: any = {};
    Object.entries(f).forEach(([k, v]) => { body[k] = v === "" ? null : k === "date" || k === "note" ? v : Number(v); });
    if (await act.run(() => post(`/api/experiments/${x.id}/events`, body))) { setF(blank); reload(); }
  };
  const doImport = async (fl: File) => {
    const fd = new FormData(); fd.append("file", fl);
    const r = await act.run(() => upload(`/api/experiments/${x.id}/import`, fd));
    if (r) { setImp(r.result); reload(); }
  };
  const rm = async (path: string) => { if (await act.run(() => del(path))) reload(); };
  const fields: [string, string][] = [["date", "Date"], ["impressions", "Impressions"], ["clicks", "Clicks"], ["landing_visits", "Landing visits"], ["checkout_visits", "Checkout visits"],
    ["purchases", "Purchases"], ["gross_revenue", "Gross $"], ["refunds", "Refunds #"], ["refund_amount", "Refunds $"], ["payment_fees", "Fees $"], ["other_costs", "Other costs $"]];
  return (
    <div className="card">
      <div className="card-head"><h2>Record results</h2>
        <div className="row"><button className="btn sm" onClick={() => file.current?.click()} disabled={act.busy}>Import CSV</button>
          <input ref={file} type="file" accept=".csv,text/csv" hidden onChange={(e) => { const fl = e.target.files?.[0]; if (fl) doImport(fl); e.target.value = ""; }} /></div></div>
      <p className="small muted">Enter real numbers from your analytics and checkout, or import a CSV — daily results (impressions, clicks, visits, checkouts, orders, revenue, costs) or an order export (Stripe, Gumroad, Shopify: order ID + amount). Re-importing the same file won't double count.</p>
      {imp && <div className={`notice ${imp.errors?.length ? "warn" : "good"} small mb`}>Imported {imp.imported} {imp.kind === "orders" ? "orders" : "result rows"}{imp.skipped_duplicates ? `, skipped ${imp.skipped_duplicates} already imported` : ""}.
        {imp.errors?.length ? <ul className="bul">{imp.errors.map((e: string) => <li key={e}>{e}</li>)}</ul> : null}</div>}
      <div className="grid" style={{ gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
        {fields.map(([k, l]) => (
          <label key={k} className="field" style={{ marginBottom: 6 }}><span>{l}</span><input type={k === "date" ? "date" : "number"} min="0" step="any" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
        ))}
        <label className="field" style={{ marginBottom: 6 }}><span>&nbsp;</span><button className="btn primary" onClick={add} disabled={act.busy}>Add row</button></label>
      </div>
      <ErrorBox error={act.error} />
      {x.events.length > 0 && (
        <div className="table-wrap mt">
          <table className="t small">
            <thead><tr>{fields.map(([k, l]) => <th key={k} className={k === "date" ? "" : "num"}>{l}</th>)}<th>Origin</th><th /></tr></thead>
            <tbody>{x.events.map((e: any) => (
              <tr key={e.id}>{fields.map(([k]) => <td key={k} className={k === "date" ? "nowrap" : "num"}>{k === "date" ? date(e.date) : <V v={e[k]} kind={k.includes("revenue") || k.includes("amount") || k.includes("fees") || k.includes("costs") ? "usd" : "num"} />}</td>)}
                <td className="muted">{e.origin}</td><td><button className="btn ghost sm" onClick={() => rm(`/api/events/${e.id}`)}>✕</button></td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {x.orders.length > 0 && (
        <>
          <h3 className="mt2">Imported orders ({x.orders.length})</h3>
          <div className="table-wrap" style={{ maxHeight: 260, overflow: "auto" }}>
            <table className="t small">
              <thead><tr><th>Order</th><th>Date</th><th className="num">Amount</th><th className="num">Refunded</th><th className="num">Fee</th><th /></tr></thead>
              <tbody>{x.orders.map((o: any) => (
                <tr key={o.id}><td className="mono">{o.order_ref}</td><td>{date(o.date)}</td><td className="num">{money(o.amount)}</td><td className="num">{o.refunded_amount ? money(o.refunded_amount) : "—"}</td>
                  <td className="num"><V v={o.fee} kind="usd" /></td><td><button className="btn ghost sm" onClick={() => rm(`/api/orders/${o.id}`)}>✕</button></td></tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Metrics({ x }: { x: any }) {
  const m = x.metrics;
  return (
    <div className="card">
      <h2>Measured performance</h2>
      {!m.has_data ? <p className="muted small">No results recorded yet.</p> : (
        <>
          {m.notes.filter((n: string) => n.includes("were used")).map((n: string) => <div key={n} className="notice warn small mb">{n}</div>)}
          <table className="t small">
            <tbody>{m.metrics.map((r: any) => (
              <tr key={r.key}><td>{r.label}{r.estimated && <span className="badge warn" style={{ marginLeft: 6 }}>estimated</span>}
                <div className="tiny faint">{r.formula}</div></td>
                <td className="num strong" style={{ whiteSpace: "nowrap" }}><V v={r.value} kind={r.unit === "pct" ? "pct" : r.unit === "usd" ? "usd" : "num"} /></td></tr>
            ))}</tbody>
          </table>
          {m.purchase_conversion_ci95 && <p className="small mt">95% interval for visitor → purchase: <b>{m.purchase_conversion_ci95[0]}% – {m.purchase_conversion_ci95[1]}%</b> (Wilson). Wide intervals mean the sample is too small to be sure.</p>}
          {m.notes.filter((n: string) => !n.includes("were used")).map((n: string) => <div key={n} className="small muted mt">{n}</div>)}
        </>
      )}
    </div>
  );
}

function Decision({ x, reload }: { x: any; reload: () => void }) {
  const ev = x.evaluation;
  const [note, setNote] = useState(x.decision_note || "");
  const act = useAsync();
  const decide = async (d: string) => { if (await act.run(() => post(`/api/experiments/${x.id}/decision`, { decision: d, note }))) reload(); };
  const tone = ev.recommendation === "go" ? "good" : ev.recommendation === "stop" ? "bad" : ev.recommendation === "revise" ? "warn" : "info";
  return (
    <div className="card">
      <h2>Go / no-go</h2>
      <div className={`notice ${tone}`}><b>Recommendation: {REC_TEXT[ev.recommendation]}</b><div className="small">{ev.reason}</div></div>
      {ev.criteria.length > 0 && (
        <table className="t small mt">
          <thead><tr><th>Criterion</th><th className="num">Observed</th><th>Met?</th></tr></thead>
          <tbody>{ev.criteria.map((c: any, i: number) => (
            <tr key={i}><td>{c.label} {c.op} {c.unit === "usd" ? "$" : ""}{c.value}{c.unit === "pct" ? "%" : ""}</td><td className="num"><V v={c.observed} kind={c.unit === "pct" || c.unit === "usd" ? c.unit : "num"} /></td>
              <td>{c.no_threshold ? <span className="badge warn">set a threshold</span> : c.met === null ? <span className="badge">not measurable yet</span> : c.met ? <span className="badge good">yes</span> : <span className="badge bad">no</span>}</td></tr>
          ))}</tbody>
        </table>
      )}
      <label className="field mt"><span>Decision note</span><textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <div className="row">
        <button className="btn accent" onClick={() => decide("go")} disabled={act.busy}>Go</button>
        <button className="btn" onClick={() => decide("revise")} disabled={act.busy}>Revise</button>
        <button className="btn danger" onClick={() => decide("stop")} disabled={act.busy}>Stop</button>
        {x.decision && <span className="small muted">Recorded: <Status s={x.decision} />{ev.recommendation && x.decision !== ev.recommendation && REC_TEXT[ev.recommendation] ? <> — overrides the app's recommendation ({ev.recommendation})</> : null}</span>}
      </div>
      <p className="tiny faint mt">Your decision is recorded next to the app's recommendation. Go marks the opportunity validated; Stop rejects it.</p>
      <ErrorBox error={act.error} />
    </div>
  );
}

export default function ExperimentDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { data: x, error, loading, reload } = useApi<any>(`/api/experiments/${id}`);
  const act = useAsync();
  if (loading) return <div className="page"><Loading /></div>;
  if (error || !x) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  const remove = async () => { if (window.confirm("Delete this experiment and its results?") && (await act.run(() => del(`/api/experiments/${id}`)))) nav("/validation"); };
  const t = x.metrics.totals;
  return (
    <div className="page">
      <div className="crumbs"><Link to="/validation">Validation Lab</Link> / <Link to={`/audiences/${x.audience_id}/experiments`}>{x.audience_name}</Link></div>
      <div className="page-head">
        <div>
          <div className="row" style={{ gap: 8 }}><h1>{x.name}</h1><Status s={x.status} /><Demo on={x.is_demo} /></div>
          <div className="sub">{x.opportunity_id ? <>Testing <Link to={`/opportunities/${x.opportunity_id}`}>{x.opportunity_name}</Link> · </> : null}
            {money(x.price)} · {num(t.landing_visits)} visitors{x.target_exposure ? ` of ${num(x.target_exposure)} planned` : ""} · {num(x.metrics.values.purchases)} purchases · {pct(x.metrics.values.purchase_conversion)} conversion</div>
        </div>
        <button className="btn ghost danger" onClick={remove}>Delete</button>
      </div>
      <div className="notice info small mb">AudienceOS doesn't take payments — use your own checkout link (Stripe Payment Link, Gumroad, Lemon Squeezy…), then import the results here.</div>
      <div className="grid g-side">
        <div className="stack">
          <Setup x={x} reload={reload} />
          <Results x={x} reload={reload} />
          {x.opportunity_id && <AssetPanel opportunityId={x.opportunity_id} experimentId={x.id} assets={x.assets} reload={reload} />}
        </div>
        <div className="stack">
          <Decision x={x} reload={reload} />
          <Metrics x={x} />
        </div>
      </div>
    </div>
  );
}
