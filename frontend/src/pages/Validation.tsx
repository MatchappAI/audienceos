import { useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { money, num, pct } from "../format";
import { Demo, Empty, ErrorBox, Loading, Status, useApi, useAsync } from "../components/ui";

export const REC_TEXT: Record<string, string> = {
  pending: "No results yet", define: "Needs success criteria", continue: "Keep running", go: "Go", revise: "Revise", stop: "Stop",
};

export function ExperimentList({ audienceId, selectable, selected, onToggle }: {
  audienceId?: string; selectable?: boolean; selected?: string[]; onToggle?: (id: string) => void;
}) {
  const { data, error, loading, reload } = useApi<any[]>(`/api/experiments${audienceId ? `?audience_id=${audienceId}` : ""}`);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data || data.length === 0)
    return <div className="card"><Empty title="No experiments yet">Open a product opportunity and choose “Create validation experiment”. Experiments test real purchasing intent with predefined success criteria.</Empty></div>;
  return (
    <div className="card" style={{ padding: 0 }}>
      <table className="t">
        <thead><tr>{selectable && <th style={{ paddingLeft: 20 }} />}<th style={selectable ? {} : { paddingLeft: 20 }}>Experiment</th><th>Status</th>
          <th className="num">Visitors</th><th className="num">Purchases</th><th className="num">Visitor → purchase</th><th className="num">Net sales</th><th className="num">Contribution</th><th>Recommendation</th><th>Decision</th></tr></thead>
        <tbody>
          {data.map((x) => (
            <tr key={x.id}>
              {selectable && <td style={{ paddingLeft: 20 }}><input type="checkbox" checked={selected?.includes(x.id)} onChange={() => onToggle?.(x.id)} aria-label={`Compare ${x.name}`} /></td>}
              <td style={selectable ? {} : { paddingLeft: 20 }}>
                <div className="row" style={{ gap: 6 }}><Link className="strong" to={`/validation/${x.id}`}>{x.name}</Link><Demo on={x.is_demo} /></div>
                <div className="small muted">{x.audience_name}{x.channel ? ` · ${x.channel}` : ""}{x.price != null ? ` · ${money(x.price)}` : ""}</div>
              </td>
              <td><Status s={x.status} /></td>
              <td className="num">{num(x.visits)}</td>
              <td className="num">{num(x.summary.purchases)}</td>
              <td className="num">{pct(x.summary.purchase_conversion)}</td>
              <td className="num">{money(x.summary.net_sales)}</td>
              <td className="num">{money(x.summary.contribution_margin)}</td>
              <td><span className={`badge ${x.recommendation === "go" ? "good" : x.recommendation === "stop" ? "bad" : x.recommendation === "revise" ? "warn" : ""}`}>{REC_TEXT[x.recommendation] || x.recommendation}</span></td>
              <td>{x.decision ? <Status s={x.decision} /> : <span className="faint">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CMP_ROWS: [string, string, string][] = [
  ["Impressions", "t:impressions", "num"], ["Landing visits", "t:landing_visits", "num"], ["Purchases", "purchases", "num"],
  ["Click-through rate", "ctr", "pct"], ["Visitor → purchase", "purchase_conversion", "pct"], ["Checkout → purchase", "checkout_conversion", "pct"],
  ["Net sales", "net_sales", "usd"], ["Contribution", "contribution_margin", "usd"], ["Revenue per visitor", "revenue_per_visitor", "usd"],
  ["Refund rate", "refund_rate", "pct"],
];

export default function Validation() {
  const [sel, setSel] = useState<string[]>([]);
  const [cmp, setCmp] = useState<any[] | null>(null);
  const act = useAsync();
  const toggle = (id: string) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id].slice(-6));
  const compare = async () => { const r = await act.run(() => get(`/api/experiments-compare?ids=${sel.join(",")}`)); if (r) setCmp(r); };
  const fmt = (v: any, k: string) => (k === "pct" ? pct(v) : k === "usd" ? money(v) : num(v));
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Validation Lab</h1>
          <div className="sub">Test real purchasing intent. AudienceOS doesn't take payments — use your own checkout link, then import the results here.</div>
        </div>
        <button className="btn" onClick={compare} disabled={sel.length < 2 || act.busy}>Compare selected ({sel.length})</button>
      </div>
      <ErrorBox error={act.error} />
      <ExperimentList selectable selected={sel} onToggle={toggle} />
      {cmp && (
        <div className="card mt2">
          <div className="card-head"><h2>Comparison</h2><button className="btn ghost sm" onClick={() => setCmp(null)}>Close</button></div>
          <p className="small muted">Each rate keeps its own denominator. 95% intervals show how uncertain small samples are.</p>
          <table className="t">
            <thead><tr><th>Metric</th>{cmp.map((x) => <th key={x.id} className="num">{x.name}</th>)}</tr></thead>
            <tbody>
              <tr><td>Price · channel</td>{cmp.map((x) => <td key={x.id} className="num small">{money(x.price)} · {x.channel || "—"}</td>)}</tr>
              {CMP_ROWS.map(([l, k, u]) => (
                <tr key={k}><td>{l}</td>{cmp.map((x) => <td key={x.id} className="num">{fmt(k.startsWith("t:") ? x.totals[k.slice(2)] : x.values[k], u)}</td>)}</tr>
              ))}
              <tr><td>95% interval, visitor → purchase</td>{cmp.map((x) => <td key={x.id} className="num small">{x.ci ? `${x.ci[0]}% – ${x.ci[1]}%` : "—"}</td>)}</tr>
              <tr><td>Recommendation</td>{cmp.map((x) => <td key={x.id} className="num">{REC_TEXT[x.recommendation]}</td>)}</tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
