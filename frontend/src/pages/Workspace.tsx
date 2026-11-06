import { useState } from "react";
import { Link, NavLink, Navigate, useNavigate, useParams } from "react-router-dom";
import { del, patch, post } from "../api";
import { compact, date, dateTime, num, platformLabel } from "../format";
import { Bullets, Demo, Empty, ErrorBox, JobLine, Loading, Modal, Stat, Status, useApi, useAsync, useJobs, useToast } from "../components/ui";
import SourcesTab from "./Sources";
import { ProblemsView, ProfileView, SignalsView } from "./Intelligence";
import { OpportunityList } from "./Opportunities";
import { ExperimentList } from "./Validation";
import { ProductList } from "./Creators";
import { CHANNEL_PLATFORMS } from "./Research";

const TABS = [
  ["", "Overview"], ["sources", "Content & sources"], ["problems", "Audience problems"], ["signals", "Commercial signals"],
  ["opportunities", "Opportunities"], ["experiments", "Experiments"], ["products", "Products"], ["reports", "Reports"],
];

export default function Workspace() {
  const { id = "", tab = "" } = useParams();
  const known = TABS.some(([k]) => k === tab);
  const { data: a, error, loading, reload } = useApi<any>(`/api/audiences/${id}`);
  if (!known) return <Navigate to={`/audiences/${id}`} replace />;
  if (loading) return <div className="page"><Loading /></div>;
  if (error || !a) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  return (
    <div className="page">
      <div className="crumbs"><Link to="/audiences">Audience Research</Link> / {a.org_name}</div>
      <div className="page-head">
        <div>
          <div className="row" style={{ gap: 8 }}><h1>{a.name}</h1><Demo on={a.is_demo} /></div>
          <div className="sub">
            {a.niche || "No niche set"} · {a.channels.length} channel{a.channels.length === 1 ? "" : "s"}
            {a.audience_size ? ` · ${compact(a.audience_size)} followers (sum of channels; may overlap)` : ""}
          </div>
        </div>
      </div>
      {a.is_demo ? <div className="notice warn mb">Demonstration data — synthetic, not a real audience.</div> : null}
      <div className="tabs" role="tablist">
        {TABS.map(([k, l]) => (
          <NavLink key={k} to={`/audiences/${id}${k ? "/" + k : ""}`} end className={() => (tab === k ? "active" : "")}>{l}</NavLink>
        ))}
      </div>
      {tab === "" && <Overview a={a} reload={reload} />}
      {tab === "sources" && <SourcesTab audience={a} reloadAudience={reload} />}
      {tab === "problems" && <><AnalyzePanel a={a} compact /><div className="mt2"><ProblemsView audienceId={id} /></div></>}
      {tab === "signals" && <SignalsView audienceId={id} />}
      {tab === "opportunities" && <OpportunityList audienceId={id} />}
      {tab === "experiments" && <ExperimentList audienceId={id} />}
      {tab === "products" && <ProductList audienceId={id} />}
      {tab === "reports" && <Reports audienceId={id} analyzed={!!a.last_analyzed_at} />}
    </div>
  );
}

export function AnalyzePanel({ a, compact: small }: { a: any; compact?: boolean }) {
  const { data: sys } = useApi<any>("/api/system");
  const { jobs, kick } = useJobs();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const { busy, error, run } = useAsync();
  const running = jobs.find((j) => j.audience_id === a.id && j.kind === "analyze_audience");
  const importing = jobs.filter((j) => j.audience_id === a.id && j.kind === "ingest_source");
  const prov = sys?.providers?.find((p: any) => p.name === sys.active_provider);
  const lastFailed = (a.jobs || []).find((j: any) => j.kind === "analyze_audience");
  const hasMaterial = a.counts.content_items + a.counts.comments > 0;

  const go = async () => {
    const r = await run(() => post(`/api/audiences/${a.id}/analyze`, { confirm_external: confirm }));
    if (r) {
      kick();
      toast(r.already_running ? "Analysis already running" : "Analysis started");
    }
  };

  return (
    <div className="card">
      <div className="row between top">
        <div style={{ maxWidth: 640 }}>
          <h2>{a.last_analyzed_at ? "Reanalyze audience" : "Analyze audience"}</h2>
          {prov ? (
            <p className="small">
              Uses <b>{prov.label}{prov.model ? ` · ${prov.model}` : ""}</b>.{" "}
              {prov.external ? (
                <span className="badge warn">Sends material to an external provider</span>
              ) : (
                <span className="badge good">Data stays on this Mac</span>
              )}{" "}
              {!prov.is_llm && <span className="muted">Keyword rules only — product ideas need an AI model.</span>}
            </p>
          ) : <p className="small muted">Checking AI provider…</p>}
          {prov && !prov.available && (
            <div className="notice warn small">{prov.detail} <Link to="/settings">Open Settings</Link></div>
          )}
          {prov?.external && (
            <label className="check small">
              <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
              <span>I understand this audience's content and comments will be sent to {prov.label}.</span>
            </label>
          )}
          {!small && (
            <p className="small muted">
              Stages: content classification → problem extraction (every quote is checked against the source) →
              clustering → commercial intent → opportunities → scoring. On the local 7B model a small audience (about
              70 comments and a few posts) takes roughly 10–15 minutes; you can keep working while it runs.
            </p>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          {running ? (
            <JobLine job={running} />
          ) : (
            <button className="btn primary" onClick={go}
              disabled={busy || !hasMaterial || !prov?.available || (prov?.external && !confirm)}>
              {busy ? "Starting…" : a.last_analyzed_at ? "Reanalyze" : "Run analysis"}
            </button>
          )}
          {!hasMaterial && <div className="small muted mt">Add content first.</div>}
          {importing.length > 0 && !running && <div className="small muted mt">{importing.length} import(s) still processing</div>}
        </div>
      </div>
      <ErrorBox error={error} />
      {lastFailed?.status === "failed" && !running && (
        <div className="notice bad small mt">Last analysis failed: {lastFailed.error}</div>
      )}
    </div>
  );
}

function ChannelEditor({ a, reload }: { a: any; reload: () => void }) {
  const [form, setForm] = useState<any | null>(null);
  const { error, run, busy } = useAsync();
  const save = async () => {
    const body = { platform: form.platform, handle: form.handle || null, url: form.url || null,
      follower_count: form.follower_count === "" || form.follower_count === null ? null : Number(String(form.follower_count).replace(/[, ]/g, "")) };
    const r = await run(() => (form.id ? patch(`/api/channels/${form.id}`, body) : post(`/api/audiences/${a.id}/channels`, body)));
    if (r) { setForm(null); reload(); }
  };
  const remove = async (cid: string) => {
    if (await run(() => del(`/api/channels/${cid}`))) reload();
  };
  return (
    <div className="card">
      <div className="card-head">
        <h2>Channels</h2>
        <button className="btn sm" onClick={() => setForm({ platform: "youtube", handle: "", url: "", follower_count: "" })}>+ Add channel</button>
      </div>
      {a.channels.length === 0 ? <p className="muted small">No channels yet. Add one so audience size can be used in scenarios.</p> : (
        <table className="t">
          <thead><tr><th>Platform</th><th>Handle</th><th className="num">Followers</th><th>Count source</th><th /></tr></thead>
          <tbody>
            {a.channels.map((c: any) => (
              <tr key={c.id}>
                <td>{platformLabel(c.platform)}</td>
                <td>{c.url ? <a href={c.url} target="_blank" rel="noreferrer noopener">{c.handle || c.url}</a> : c.handle || "—"}</td>
                <td className="num">{c.follower_count != null ? num(c.follower_count) : <span className="faint" title="not entered">—</span>}</td>
                <td className="small muted">{c.follower_count_source || "—"}</td>
                <td className="num">
                  <button className="btn ghost sm" onClick={() => setForm({ ...c, follower_count: c.follower_count ?? "" })}>Edit</button>
                  <button className="btn ghost sm danger" onClick={() => remove(c.id)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ErrorBox error={error} />
      {form && (
        <Modal title={form.id ? "Edit channel" : "Add channel"} onClose={() => setForm(null)}>
          <label className="field"><span>Platform</span>
            <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
              {CHANNEL_PLATFORMS.map((p) => <option key={p} value={p}>{platformLabel(p)}</option>)}
            </select></label>
          <label className="field"><span>Handle</span><input value={form.handle || ""} onChange={(e) => setForm({ ...form, handle: e.target.value })} /></label>
          <label className="field"><span>URL</span><input value={form.url || ""} onChange={(e) => setForm({ ...form, url: e.target.value })} /></label>
          <label className="field"><span>Followers / subscribers</span>
            <input inputMode="numeric" value={form.follower_count} onChange={(e) => setForm({ ...form, follower_count: e.target.value })} /></label>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn" onClick={() => setForm(null)}>Cancel</button>
            <button className="btn primary" onClick={save} disabled={busy}>Save</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Overview({ a, reload }: { a: any; reload: () => void }) {
  const nav = useNavigate();
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({ name: a.name, niche: a.niche || "", description: a.description || "", org_name: a.org_name });
  const { error, run, busy } = useAsync();
  const an = a.latest_analysis;
  const save = async () => {
    if (await run(() => patch(`/api/audiences/${a.id}`, f))) { setEdit(false); reload(); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete “${a.name}” and everything imported for it? This cannot be undone.`)) return;
    if (await run(() => del(`/api/audiences/${a.id}`))) nav("/audiences");
  };
  return (
    <div className="stack">
      <AnalyzePanel a={a} />
      <div className="grid g4">
        <Stat label="Sources" value={num(a.counts.sources)} hint={`${num(a.counts.content_items)} content item${a.counts.content_items === 1 ? "" : "s"}`} />
        <Stat label="Words of content" value={compact(a.counts.words)} hint={`${num(a.counts.transcripts)} transcript${a.counts.transcripts === 1 ? "" : "s"}`} />
        <Stat label="Audience comments" value={num(a.counts.comments)} hint="excl. duplicates & spam" />
        <Stat label="Opportunities" value={num(a.counts.opportunities)} hint={`${num(a.counts.experiments)} experiment${a.counts.experiments === 1 ? "" : "s"}`} />
      </div>
      {an && (
        <div className="card">
          <div className="card-head">
            <h2>Latest analysis</h2>
            <span className="row small muted"><Status s={an.status} /> {an.provider}{an.model ? ` · ${an.model}` : ""} · {dateTime(an.finished_at || an.started_at)}
              {an.external ? <span className="badge warn">external</span> : <span className="badge good">on this Mac</span>}</span>
          </div>
          {an.stats && Object.keys(an.stats).length > 0 && (
            <div className="grid g4 small">
              <div><div className="muted">Units analyzed</div><b>{num(an.stats.units)}</b></div>
              <div><div className="muted">Comments analyzed</div><b>{num(an.stats.comments_analyzed)}</b> of {num(an.stats.comments_total)}
                {an.stats.comment_sampling && <div className="tiny faint">{an.stats.comment_sampling.method === "embedding" ? `sampled across ${an.stats.comment_sampling.groups} topic groups` : "sampled by likes and recency"}</div>}</div>
              <div><div className="muted">Excluded</div><b>{num(an.stats.duplicates_excluded)}</b> duplicates · <b>{num(an.stats.spam_excluded)}</b> spam</div>
              <div><div className="muted">Unverifiable quotes discarded</div><b>{num(an.stats.rejected_quotes)}</b></div>
              <div><div className="muted">Signals</div><b>{num(an.stats.signals)}</b></div>
              <div><div className="muted">Problem themes</div><b>{num(an.stats.clusters)}</b></div>
              <div><div className="muted">Opportunities</div><b>{num(an.stats.opportunities)}</b>{an.stats.opportunities_dropped ? ` (${an.stats.opportunities_dropped} dropped: no evidence)` : ""}</div>
            </div>
          )}
          {an.unknowns?.length > 0 && (
            <div className="mt2"><h3>Important unknowns</h3><Bullets items={an.unknowns} /></div>
          )}
        </div>
      )}
      {an?.status === "done" && <ProfileView audienceId={a.id} />}
      <ChannelEditor a={a} reload={reload} />
      <div className="card">
        <div className="card-head">
          <h2>Details</h2>
          {!edit && <button className="btn sm" onClick={() => setEdit(true)}>Edit</button>}
        </div>
        {edit ? (
          <>
            <div className="grid g2">
              <label className="field"><span>Creator / business</span><input value={f.org_name} onChange={(e) => setF({ ...f, org_name: e.target.value })} /></label>
              <label className="field"><span>Audience name</span><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
            </div>
            <label className="field"><span>Niche</span><input value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })} /></label>
            <label className="field"><span>Notes</span><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
            <div className="row"><button className="btn primary" onClick={save} disabled={busy}>Save</button><button className="btn" onClick={() => setEdit(false)}>Cancel</button></div>
          </>
        ) : (
          <dl className="kv small">
            <dt>Creator / business</dt><dd>{a.org_name} <span className="muted">({a.org_kind})</span></dd>
            <dt>Niche</dt><dd>{a.niche || "—"}</dd>
            <dt>Notes</dt><dd className="prewrap">{a.description || "—"}</dd>
            <dt>Created</dt><dd>{date(a.created_at)}</dd>
          </dl>
        )}
        <ErrorBox error={error} />
        <div className="row mt2"><span className="spacer" />
          <a className="btn sm" href={`/api/audiences/${a.id}/export`}>Export all data (JSON)</a>
          <button className="btn sm danger" onClick={remove}>Delete audience</button></div>
      </div>
    </div>
  );
}

function Reports({ audienceId, analyzed }: { audienceId: string; analyzed: boolean }) {
  const { data, error, loading, reload } = useApi<any[]>(`/api/audiences/${audienceId}/reports`);
  const gen = useAsync();
  const toast = useToast();
  const make = async () => {
    if (await gen.run(() => post(`/api/audiences/${audienceId}/reports`))) { toast("Report exported"); reload(); }
  };
  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2>Research reports</h2>
          <p className="small muted" style={{ margin: 0 }}>Built only from stored data: overview, problems with quotes, purchasing signals, opportunities, experiments, unknowns and sources.</p>
        </div>
        <button className="btn primary" onClick={make} disabled={gen.busy || !analyzed} title={analyzed ? undefined : "Run an analysis first"}>{gen.busy ? "Building…" : "Generate report"}</button>
      </div>
      <ErrorBox error={gen.error || error} />
      {loading && <Loading />}
      {data && data.length === 0 && <Empty title="No reports yet">{analyzed ? "Generate a report to get HTML, PDF, JSON and CSV versions." : <>Run an analysis first — <Link to={`/audiences/${audienceId}/problems`}>go to analysis</Link>.</>}</Empty>}
      {data && data.length > 0 && (
        <table className="t">
          <thead><tr><th>Report</th><th>Created</th><th>Open</th><th>Download</th></tr></thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td className="small">{dateTime(r.created_at)}</td>
                <td className="row">
                  <a className="btn sm" href={`/api/reports/${r.id}/html`} target="_blank" rel="noreferrer">HTML</a>
                  <a className="btn sm" href={`/api/reports/${r.id}/pdf`} target="_blank" rel="noreferrer">PDF</a>
                </td>
                <td className="row">
                  <a className="btn ghost sm" href={`/api/reports/${r.id}/json?download=1`}>JSON</a>
                  <a className="btn ghost sm" href={`/api/reports/${r.id}/opportunities_csv?download=1`}>Opportunities CSV</a>
                  <a className="btn ghost sm" href={`/api/reports/${r.id}/signals_csv?download=1`}>Signals CSV</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
