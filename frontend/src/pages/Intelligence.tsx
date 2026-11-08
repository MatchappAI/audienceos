import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { compact, date, dateTime, INTENT_LABEL, num, platformLabel } from "../format";
import { Quote } from "../components/evidence";
import { Bullets, Demo, Empty, ErrorBox, Loading, Status, useApi } from "../components/ui";

function useIntel(audienceId: string) {
  return useApi<any>(`/api/audiences/${audienceId}/intelligence`);
}

function NoAnalysis({ intel, audienceId }: { intel: any; audienceId: string }) {
  const la = intel?.last_attempt;
  return (
    <div className="card">
      <Empty title={la?.status === "running" ? "Analysis in progress" : "No completed analysis yet"}
        actions={la?.status === "running" || window.location.pathname.startsWith(`/audiences/${audienceId}/problems`) ? undefined :
          <Link className="btn primary" to={`/audiences/${audienceId}/problems`}>Go to analysis</Link>}>
        {la?.status === "failed" ? (
          <span>The last attempt failed{la.unknowns?.[0] ? `: ${la.unknowns[0]}` : "."}</span>
        ) : la?.status === "running" ? "Results appear here when it finishes." :
          "Import content and comments, then run an analysis. Every finding will link back to its source."}
        {la?.status === "running" && <div className="small muted mt">You can keep working elsewhere — the analysis continues in the background and survives a restart.</div>}
      </Empty>
    </div>
  );
}

const QUALITY_TONE: Record<string, string> = { Strong: "good", Moderate: "info", Weak: "warn", "Creator content only": "" };

export function ProfileView({ audienceId }: { audienceId: string }) {
  const { data, loading, error } = useIntel(audienceId);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const p = data?.analysis?.profile;
  if (!p) return null;
  return (
    <div className="card">
      <h2>Audience overview</h2>
      <p>{p.summary}</p>
      <dl className="kv small mt">
        <dt>Intended audience</dt><dd>{p.intended_audience}</dd>
        <dt>Topics</dt><dd className="row" style={{ gap: 6 }}>{(p.topics || []).map((t: any) => <span key={t.name} className={`badge ${t.weight === "major" ? "info" : ""}`}>{t.name}</span>)}</dd>
        <dt>Problems addressed</dt><dd>{(p.problem_types || []).join(" · ") || "—"}</dd>
        <dt>Content categories</dt><dd>{(p.content_categories || []).join(" · ") || "—"}</dd>
        <dt>Credibility signals</dt><dd>{(p.credibility_signals || []).join(" · ") || "—"}</dd>
      </dl>
      {p.audience_characteristics?.length > 0 && (
        <>
          <h3 className="mt2">Audience characteristics</h3>
          <ul className="clean small">
            {p.audience_characteristics.map((c: any, i: number) => (
              <li key={i}>
                <div className="row" style={{ gap: 6 }}>{c.claim}
                  {c.supported ? <span className="badge good">supported · {c.evidence.length} excerpt{c.evidence.length > 1 ? "s" : ""}</span> : <span className="badge warn">unverified</span>}</div>
                <div className="muted">{c.basis}</div>
                {c.evidence?.length > 0 && (
                  <details className="fold"><summary>Source excerpts</summary>
                    {c.evidence.map((e: any, j: number) => <div key={j} className="quote" style={{ cursor: "default" }}><div className="q">{e.excerpt}…</div></div>)}
                  </details>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="tiny faint mt">Model interpretation of stored material. Demographics are never inferred.</p>
    </div>
  );
}

export function ProblemsView({ audienceId }: { audienceId: string }) {
  const { data, loading, error, reload } = useIntel(audienceId);
  const [open, setOpen] = useState<string | null>(null);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data?.analysis) return <NoAnalysis intel={data} audienceId={audienceId} />;
  const gaps = data.analysis.profile?.market_gaps || [];
  const labels: Record<string, string> = Object.fromEntries(data.clusters.map((c: any) => [c.id, c.label]));
  return (
    <div className="stack">
      <div className="card" style={{ padding: 0 }}>
        <div className="card-head" style={{ padding: "16px 20px 0" }}>
          <h2>Recurring problems</h2>
          <span className="small muted">Ranked by intent × distinct voices. Click a row for quotes.</span>
        </div>
        {data.clusters.length === 0 ? <Empty title="No problems found">The analysis found no audience problems in the material. Add audience comments for stronger evidence.</Empty> : (
          <table className="t">
            <thead><tr><th style={{ paddingLeft: 20 }}>Problem</th><th className="num" title="Distinct commenters (hashed); anonymous comments count individually">Voices</th>
              <th className="num">Signals</th><th className="num">Sources</th><th className="num" title="0–5, weighted by the strongest buying language per voice">Intent</th><th>Evidence</th><th className="num">Median age</th></tr></thead>
            <tbody>
              {data.clusters.map((c: any) => (
                <Fragment key={c.id}>
                  <tr className="click" onClick={() => setOpen(open === c.id ? null : c.id)}>
                    <td style={{ paddingLeft: 20 }}><div className="strong">{open === c.id ? "▾" : "▸"} {c.label}</div><div className="small muted">{c.description}</div></td>
                    <td className="num">{num(c.unique_authors)}</td>
                    <td className="num">{num(c.signal_count)}</td>
                    <td className="num">{num(c.source_count)}</td>
                    <td className="num"><div className="row" style={{ justifyContent: "flex-end", gap: 6, flexWrap: "nowrap" }}>{c.intent_score.toFixed(1)}<div className="bar" style={{ width: 50 }}><i style={{ width: `${c.intent_score * 20}%` }} /></div></div></td>
                    <td><span className={`badge ${QUALITY_TONE[c.evidence_quality] ?? ""}`}>{c.evidence_quality}</span></td>
                    <td className="num small">{c.median_age_days != null ? `${Math.round(c.median_age_days)} d` : <span className="faint" title="no dates">—</span>}</td>
                  </tr>
                  {open === c.id && (
                    <tr><td colSpan={7} style={{ paddingLeft: 32, background: "var(--panel-2)" }}>
                      <div className="small muted">Intent mix: {Object.entries(c.intent_breakdown || {}).map(([k, v]) => `${INTENT_LABEL[k] || k} ${v}`).join(" · ")}</div>
                      {c.quotes.slice(0, 12).map((q: any) => <Quote key={q.id} q={q} />)}
                      {c.quotes.length > 12 && <div className="small muted">+{c.quotes.length - 12} more in the Research Library</div>}
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="grid g3">
        <SignalGroup title="Questions followers ask" items={data.groups.questions} labels={labels} />
        <SignalGroup title="Complaints & frustrations" items={data.groups.complaints} labels={labels} />
        <SignalGroup title="Requests for solutions" items={data.groups.requests} labels={labels} />
      </div>
      {data.groups.outcomes?.length > 0 && <SignalGroup title="Desired outcomes & repetitive tasks" items={data.groups.outcomes} labels={labels} />}
      {gaps.length > 0 && (
        <div className="card">
          <h2>Market gaps <span className="badge">model interpretation</span></h2>
          <ul className="bul">{gaps.map((g: any, i: number) => <li key={i}>{g.gap}{g.cluster_ids?.length ? <span className="muted small"> — {g.cluster_ids.map((id: string) => labels[id]).filter(Boolean).join(", ")}</span> : null}</li>)}</ul>
        </div>
      )}
      <AnalysisMeta data={data} />
    </div>
  );
}

function SignalGroup({ title, items, labels }: { title: string; items: any[]; labels: Record<string, string> }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 6);
  return (
    <div className="card">
      <div className="card-head"><h2>{title}</h2><span className="badge">{items.length}</span></div>
      {items.length === 0 ? <p className="small muted">None found.</p> : shown.map((q) => <Quote key={q.id} q={q} showCluster={labels[q.cluster_id]} />)}
      {items.length > 6 && <button className="linkbtn small" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${items.length}`}</button>}
    </div>
  );
}

function AnalysisMeta({ data }: { data: any }) {
  const an = data.analysis;
  return (
    <div className="grid g2">
      <div className="card">
        <h2>Important unknowns</h2>
        <Bullets items={an.unknowns} />
      </div>
      <div className="card">
        <h2>How this was produced</h2>
        <div className="small muted mb">{an.provider}{an.model ? ` · ${an.model}` : ""} · {dateTime(an.finished_at)} · {an.external ? "external provider" : "processed on this Mac"}</div>
        <table className="t small">
          <thead><tr><th>Stage</th><th>Status</th><th>Notes</th></tr></thead>
          <tbody>{data.runs.map((r: any) => (
            <tr key={r.id}><td>{r.stage}{r.external ? <span className="badge warn" style={{ marginLeft: 6 }}>external</span> : null}</td><td><Status s={r.status} /></td><td className="muted">{r.error || r.notes || "—"}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}

export function SignalsView({ audienceId, quietEmpty }: { audienceId: string; quietEmpty?: boolean }) {
  const { data, loading, error, reload } = useIntel(audienceId);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const perf = data?.performance || [];
  return (
    <div className="stack">
      {!data?.analysis ? (quietEmpty ? null : <NoAnalysis intel={data} audienceId={audienceId} />) : (
        <>
          <div className="card">
            <h2>Commercial intent</h2>
            <p className="small muted">Strongest evidence first. Spending and buying language counts more than likes or comments — popularity is not willingness to pay.</p>
            <div className="row mt" style={{ gap: 8 }}>
              {Object.keys(INTENT_LABEL).reverse().map((k) => (
                <span key={k} className={`badge ${["verified_purchase", "paid_solution_request", "buying_question", "existing_spending"].includes(k) ? "info" : ""}`}>
                  {INTENT_LABEL[k]}: {data.intent_counts?.[k] || 0}
                </span>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h2>Purchasing signals</h2><span className="badge">{data.purchasing.length}</span></div>
            {data.purchasing.length === 0 ? (
              <div className="notice warn small">No spending or buying language was found. Willingness to pay is unproven — validate with a real offer.</div>
            ) : data.purchasing.map((q: any) => <Quote key={q.id} q={q} />)}
          </div>
        </>
      )}
      <div className="card" style={{ padding: 0 }}>
        <div className="card-head" style={{ padding: "16px 20px 0" }}><h2>Content performance</h2><span className="small muted">From imported analytics only</span></div>
        {perf.length === 0 ? <Empty title="No engagement metrics imported">Import an analytics CSV (views, likes, saves…) or add a YouTube Data API key to compare content.</Empty> : (
          <PerfTable rows={perf} />
        )}
      </div>
    </div>
  );
}

function PerfTable({ rows }: { rows: any[] }) {
  const byItem: Record<string, any> = {};
  const metrics = new Set<string>();
  rows.forEach((r) => {
    byItem[r.id] = byItem[r.id] || { ...r, m: {} };
    byItem[r.id].m[r.metric] = r.value;
    metrics.add(r.metric);
  });
  const ms = Array.from(metrics);
  const items = Object.values(byItem).sort((a: any, b: any) => (b.m.views || b.m.impressions || 0) - (a.m.views || a.m.impressions || 0));
  return (
    <table className="t">
      <thead><tr><th style={{ paddingLeft: 20 }}>Content</th><th>Published</th>{ms.map((m) => <th key={m} className="num">{m}</th>)}</tr></thead>
      <tbody>{items.map((it: any) => (
        <tr key={it.id}><td style={{ paddingLeft: 20 }}>{it.url ? <a href={it.url} target="_blank" rel="noreferrer noopener">{it.title || it.url}</a> : it.title}
          <div className="tiny faint">{platformLabel(it.platform)} · {it.source_note}</div></td>
          <td className="small">{date(it.published_at)}</td>
          {ms.map((m) => <td key={m} className="num">{it.m[m] != null ? compact(it.m[m]) : <span className="faint" title="not measured">—</span>}</td>)}</tr>
      ))}</tbody>
    </table>
  );
}

export default function IntelligencePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: auds, loading, error, reload } = useApi<any[]>("/api/audiences");
  const current = id || auds?.find((a) => a.last_analyzed_at)?.id || auds?.[0]?.id;
  const a = auds?.find((x) => x.id === current);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Audience Intelligence</h1>
          <div className="sub">What the audience struggles with and what they might pay for — every claim links to its source.</div>
        </div>
        {auds && auds.length > 0 && (
          <select value={current} onChange={(e) => nav(`/intelligence/${e.target.value}`)} style={{ width: 300 }} aria-label="Audience">
            {auds.map((x) => <option key={x.id} value={x.id}>{x.name}{x.is_demo && !/demo/i.test(x.name) ? " (demo)" : ""}</option>)}
          </select>
        )}
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {auds && auds.length === 0 && <div className="card"><Empty title="No audiences yet" actions={<Link className="btn primary" to="/audiences?new=1">Add a creator</Link>} /></div>}
      {a && (
        <div className="stack">
          <div className="row"><Link to={`/audiences/${a.id}`} className="strong">{a.name}</Link><Demo on={a.is_demo} />
            <span className="small muted">{a.last_analyzed_at ? `Analyzed ${date(a.last_analyzed_at)}` : "Not analyzed yet"}</span></div>
          <ProfileView audienceId={a.id} />
          <ProblemsView audienceId={a.id} />
          <SignalsView audienceId={a.id} quietEmpty />
        </div>
      )}
    </div>
  );
}
