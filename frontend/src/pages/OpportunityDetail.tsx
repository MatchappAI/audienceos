import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { del, get, patch, post } from "../api";
import { date, money, num } from "../format";
import { Quote } from "../components/evidence";
import { AssetPanel } from "../components/assets";
import { Bullets, Demo, ErrorBox, JobLine, Loading, Status, useApi, useAsync, useJobs, useToast } from "../components/ui";
import { INDEX_NOTE, ScoreChip } from "./Opportunities";

function ScoreTable({ o, reload }: { o: any; reload: () => void }) {
  const [edit, setEdit] = useState<Record<string, number>>({});
  const act = useAsync();
  const save = async () => { if (await act.run(() => patch(`/api/opportunities/${o.id}`, { scores: edit }))) { setEdit({}); reload(); } };
  return (
    <div className="card">
      <div className="card-head"><h2>Score breakdown</h2><span className="row"><ScoreChip v={o.total_score} /><span className="small muted">/ 100</span></span></div>
      <p className="small muted">{INDEX_NOTE} Index = Σ weight × (score − 1)/4 ÷ Σ weights. “Data” criteria are computed from stored evidence; “model” criteria are the AI's ratings — you can override them. Weights are set in Settings.</p>
      <table className="t">
        <thead><tr><th>Criterion</th><th className="num">Weight</th><th>Source</th><th className="num">Score (1–5)</th></tr></thead>
        <tbody>{o.score_breakdown.map((s: any) => (
          <tr key={s.key}><td>{s.label}</td><td className="num">{s.weight}</td><td><span className={`badge ${s.source === "data" ? "info" : ""}`}>{s.source}</span></td>
            <td className="num">{s.source === "model" ? (
              <select value={edit[s.key] ?? s.score ?? ""} onChange={(e) => setEdit({ ...edit, [s.key]: Number(e.target.value) })} style={{ width: 64 }} aria-label={s.label}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>) : (s.score ?? "—")}</td></tr>
        ))}</tbody>
      </table>
      {o.confidence?.score_rationale && <p className="small muted mt">Model's rationale: {o.confidence.score_rationale}</p>}
      {Object.keys(edit).length > 0 && <div className="row mt"><button className="btn primary sm" onClick={save} disabled={act.busy}>Save scores</button><button className="btn sm" onClick={() => setEdit({})}>Reset</button></div>}
      <ErrorBox error={act.error} />
    </div>
  );
}

function Economics({ o, reload }: { o: any; reload: () => void }) {
  const sc = o.scenario || {};
  const [f, setF] = useState<any>({});
  useEffect(() => {
    setF({
      price: o.price ?? "", production_cost: o.production_cost ?? "", fulfillment_cost_per_unit: o.fulfillment_cost_per_unit ?? "",
      reach: sc.reach ?? "", exposure_pct: sc.exposure_pct ?? "", rates: (sc.rates_pct || []).join(", "),
      payment_fee_pct: sc.payment_fee_pct ?? 3, payment_fee_fixed: sc.payment_fee_fixed ?? 0.3,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [o.id, o.updated_at]);
  const act = useAsync();
  const n = (v: any) => (v === "" || v === null || v === undefined ? null : Number(v));
  const save = async () => {
    const body = {
      price: n(f.price) ?? undefined, production_cost: n(f.production_cost) ?? undefined, fulfillment_cost_per_unit: n(f.fulfillment_cost_per_unit) ?? undefined,
      scenario: { reach: n(f.reach), exposure_pct: n(f.exposure_pct), payment_fee_pct: n(f.payment_fee_pct) ?? 0, payment_fee_fixed: n(f.payment_fee_fixed) ?? 0,
        rates_pct: String(f.rates).split(/[,\s]+/).filter(Boolean).map(Number).filter((x) => isFinite(x) && x >= 0).slice(0, 6) },
    };
    if (await act.run(() => patch(`/api/opportunities/${o.id}`, body))) reload();
  };
  const r = o.scenario_result;
  const inp = (k: string, label: string, suffix?: string) => (
    <label className="field"><span>{label}{suffix ? ` (${suffix})` : ""}</span><input inputMode="decimal" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
  );
  return (
    <div className="card">
      <h2>Economics & scenarios</h2>
      <p className="small muted">All inputs are assumptions you control. Purchase rates are not benchmarks — enter rates you want to stress-test.</p>
      <div className="grid g4">
        {inp("price", "Test price", "$")}{inp("production_cost", "One-time production cost", "$")}{inp("fulfillment_cost_per_unit", "Fulfillment cost per sale", "$")}
        {inp("payment_fee_pct", "Payment fee", "%")}{inp("payment_fee_fixed", "Fixed fee per sale", "$")}
        {inp("reach", "Audience reach", "people")}{inp("exposure_pct", "Share who see the offer", "%")}{inp("rates", "Purchase rates to model", "% list")}
      </div>
      <div className="row"><button className="btn primary sm" onClick={save} disabled={act.busy}>Recalculate</button><ErrorBox error={act.error} /></div>
      <div className="grid g3 mt2">
        <div className="stat"><div className="label">Contribution per sale</div><div className="value">{money(r.unit_contribution)}</div><div className="hint">after {money(r.fee_per_sale)} payment fees{o.fulfillment_cost_per_unit ? ` + ${money(o.fulfillment_cost_per_unit)} fulfillment` : ""}</div></div>
        <div className="stat"><div className="label">Break-even sales</div><div className="value">{r.breakeven_units == null ? "—" : num(r.breakeven_units)}</div><div className="hint">to recover production cost</div></div>
        <div className="stat"><div className="label">Price model</div><div className="value" style={{ fontSize: 18 }}>{o.price_model}</div><div className="hint">Recurring: {o.recurring}</div></div>
      </div>
      {r.warnings?.map((w: string) => <div key={w} className="notice warn small mt">{w}</div>)}
      {r.rows?.length > 0 && (
        <table className="t mt">
          <thead><tr><th className="num">Purchase rate</th><th className="num">People who see it</th><th className="num">Buyers</th><th className="num">Gross revenue</th><th className="num">Net contribution</th></tr></thead>
          <tbody>{r.rows.map((x: any) => <tr key={x.rate_pct}><td className="num">{x.rate_pct}%</td><td className="num">{num(x.exposed)}</td><td className="num">{num(x.buyers, 1)}</td><td className="num">{money(x.gross_revenue, 0)}</td>
            <td className="num" style={{ color: x.net_contribution < 0 ? "var(--bad)" : undefined }}>{money(x.net_contribution, 0)}</td></tr>)}</tbody>
        </table>
      )}
      <details className="fold mt"><summary>Formulas</summary><ul className="bul small">{r.formulas.map((x: string) => <li key={x}>{x}</li>)}</ul></details>
    </div>
  );
}

function Competitors({ o, reload }: { o: any; reload: () => void }) {
  const [f, setF] = useState({ name: "", url: "", price_text: "" });
  const [note, setNote] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobErr, setJobErr] = useState<string | null>(null);
  const act = useAsync();
  const { jobs, kick } = useJobs();
  const running = jobId ? jobs.find((j) => j.id === jobId) : null;
  useEffect(() => {
    if (jobId && !running) {
      get(`/api/jobs/${jobId}`).then((j: any) => {
        if (j.status === "failed") setJobErr(j.error);
        if (j.status === "done") reload();
        if (j.status !== "queued" && j.status !== "running") setJobId(null);
      }).catch(() => setJobId(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, running]);
  const add = async () => {
    const r = await act.run(() => post(`/api/audiences/${o.audience_id}/competitors`, { ...f, url: f.url || null, price_text: f.price_text || null, opportunity_id: o.id }));
    if (r) { setNote(r.note); setF({ name: "", url: "", price_text: "" }); reload(); }
  };
  const auto = async () => { setJobErr(null); const r = await act.run(() => post(`/api/opportunities/${o.id}/research`)); if (r) { setJobId(r.job_id); kick(); } };
  const remove = async (id: string) => { if (await act.run(() => del(`/api/competitors/${id}`))) reload(); };
  return (
    <div className="card">
      <div className="card-head"><h2>Competitors & alternatives</h2>
        {running ? <JobLine job={running} /> : <button className="btn sm" onClick={auto} disabled={act.busy}>Auto-research (web)</button>}</div>
      <div className="notice small mb"><b>Model's general knowledge (unverified):</b> {o.competition_notes || "—"}</div>
      {jobErr && <div className="notice warn small mb">{jobErr}</div>}
      {o.competitors.length > 0 && (
        <table className="t mb">
          <thead><tr><th>Name</th><th>Prices seen</th><th>Provenance</th><th /></tr></thead>
          <tbody>{o.competitors.map((c: any) => (
            <tr key={c.id}><td>{c.url ? <a href={c.url} target="_blank" rel="noreferrer noopener">{c.name}</a> : c.name}<div className="tiny faint clip" style={{ maxWidth: 360 }}>{c.description}</div></td>
              <td className="small">{c.price_text || <span className="faint">not visible</span>}</td>
              <td className="small"><span className={`badge ${c.provenance === "retrieved" ? "good" : ""}`}>{c.provenance}</span>{c.retrieved_at ? <div className="tiny faint">{date(c.retrieved_at)}</div> : null}</td>
              <td className="num"><button className="btn ghost sm" onClick={() => remove(c.id)}>Remove</button></td></tr>
          ))}</tbody>
        </table>
      )}
      <div className="grid" style={{ gridTemplateColumns: "1fr 1.4fr 0.8fr auto", gap: 8 }}>
        <input placeholder="Competitor name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} aria-label="Competitor name" />
        <input placeholder="Product page URL (prices are read from it)" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} aria-label="URL" />
        <input placeholder="Price (optional)" value={f.price_text} onChange={(e) => setF({ ...f, price_text: e.target.value })} aria-label="Price" />
        <button className="btn" onClick={add} disabled={act.busy || !f.name.trim()}>Add</button>
      </div>
      {note && <div className="small muted mt">{note}</div>}
      <ErrorBox error={act.error} />
    </div>
  );
}

export default function OpportunityDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data: o, error, loading, reload } = useApi<any>(`/api/opportunities/${id}`);
  const act = useAsync();
  if (loading) return <div className="page"><Loading /></div>;
  if (error || !o) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  const setSt = async (s: string) => { if (await act.run(() => patch(`/api/opportunities/${id}`, { status: s }))) { toast(`Marked ${s}`); reload(); } };
  const mkExp = async () => { const r = await act.run(() => post("/api/experiments", { opportunity_id: id })); if (r) nav(`/validation/${r.id}`); };
  const mkProd = async () => { const r = await act.run(() => post("/api/products", { opportunity_id: id })); if (r) nav(`/products/${r.id}`); };
  const conf = o.confidence || {};
  return (
    <div className="page">
      <div className="crumbs"><Link to="/opportunities">Product Opportunities</Link> / <Link to={`/audiences/${o.audience_id}/opportunities`}>{o.audience_name}</Link></div>
      <div className="page-head">
        <div>
          <div className="row" style={{ gap: 10 }}><ScoreChip v={o.total_score} /><h1>{o.name}</h1><Status s={o.status} /><Demo on={o.is_demo} /></div>
          <div className="sub">{o.product_type} · test at {money(o.price)} {o.price_model} · {o.delivery_difficulty} delivery difficulty</div>
        </div>
        <div className="row">
          {o.status === "proposed" && <button className="btn" onClick={() => setSt("approved")} disabled={act.busy}>Approve for testing</button>}
          {o.status !== "rejected" && <button className="btn ghost" onClick={() => setSt("rejected")} disabled={act.busy}>Reject</button>}
          {o.status === "rejected" && <button className="btn ghost" onClick={() => setSt("proposed")}>Restore</button>}
          {/* Once an experiment or product exists, open it instead of silently creating a duplicate. */}
          {o.products?.length ? <Link className="btn" to={`/products/${o.products[0].id}`}>Open product</Link>
            : <button className="btn" onClick={mkProd} disabled={act.busy}>Create product</button>}
          {o.experiments?.length ? <>
            <button className="btn ghost" onClick={mkExp} disabled={act.busy}>New experiment</button>
            <Link className={`btn ${o.products?.length ? "" : "primary"}`} to={`/validation/${o.experiments[0].id}`}>Open experiment</Link>
          </> : <button className="btn primary" onClick={mkExp} disabled={act.busy}>Create validation experiment</button>}
        </div>
      </div>
      <ErrorBox error={act.error} />
      {(o.experiments.length > 0 || o.products.length > 0) && (
        <div className="notice info small mb">
          {o.experiments.map((x: any) => <span key={x.id} style={{ marginRight: 14 }}>Experiment: <Link to={`/validation/${x.id}`}>{x.name}</Link> <Status s={x.decision || x.status} /></span>)}
          {o.products.map((p: any) => <span key={p.id} style={{ marginRight: 14 }}>Product: <Link to={`/products/${p.id}`}>{p.name}</Link> <Status s={p.status} /></span>)}
        </div>
      )}
      <div className="grid g-side">
        <div className="stack">
          <div className="card">
            <dl className="kv">
              <dt>Product</dt><dd>{o.name} <span className="muted">({o.product_type})</span></dd>
              <dt>Buyer</dt><dd>{o.buyer}</dd>
              <dt>Problem</dt><dd>{o.problem}</dd>
              <dt>Why this format</dt><dd>{o.format_rationale}</dd>
              <dt>Price to test</dt><dd><b>{money(o.price)}</b> {o.price_model} — <span className="muted">{o.price_rationale}</span></dd>
              <dt>Production</dt><dd>{o.production}</dd>
              <dt>Economics</dt><dd>{money(o.production_cost, 0)} to produce · {money(o.fulfillment_cost_per_unit)} per sale to fulfill <span className="muted">(estimates)</span></dd>
              <dt>Recurring revenue</dt><dd>{o.recurring}</dd>
              <dt>Distribution</dt><dd>{o.distribution}</dd>
              <dt>Validation test</dt><dd>{o.validation_plan}</dd>
            </dl>
          </div>
          <div className="card">
            <div className="card-head"><h2>Supporting evidence</h2><span className="badge">{o.evidence.length} verbatim quotes</span></div>
            {o.evidence.map((e: any) => <Quote key={e.id} q={{ ...e, evidence_id: e.id }} />)}
            {o.clusters.length > 0 && <div className="small muted mt">Problems addressed: {o.clusters.map((c: any) => `${c.label} (${c.unique_authors} voices, intent ${Number(c.intent_score).toFixed(1)}, ${c.evidence_quality})`).join(" · ")}</div>}
          </div>
          <Economics o={o} reload={reload} />
          <Competitors o={o} reload={reload} />
          <AssetPanel opportunityId={o.id} assets={o.assets} reload={reload} />
        </div>
        <div className="stack">
          <div className="card">
            <h2>Confidence</h2>
            <h3 className="mt" style={{ color: "var(--good)" }}>Supported by evidence</h3><Bullets items={conf.supported} />
            <h3 className="mt" style={{ color: "var(--warn)" }}>Assumed</h3><Bullets items={conf.assumed} />
            <h3 className="mt">Unknown</h3><Bullets items={conf.unknown} />
          </div>
          {(() => {
            const seen = new Set((conf.unknown || []).map((u: string) => u.trim().toLowerCase()));
            const extra = (o.missing_evidence || []).filter((m: string) => !seen.has(m.trim().toLowerCase()));
            return extra.length > 0 ? <div className="card"><h2>Missing evidence</h2><Bullets items={extra} /></div> : null;
          })()}
          <div className="card"><h2>Risks</h2><Bullets items={o.risks} /></div>
          <ScoreTable o={o} reload={reload} />
          {o.run && <div className="small muted">Generated by {o.run.provider} {o.run.model} {o.run.external ? "(external)" : "(on this Mac)"} · {date(o.run.finished_at)}</div>}
        </div>
      </div>
    </div>
  );
}
