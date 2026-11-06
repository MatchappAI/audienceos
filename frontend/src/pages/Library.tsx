import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../api";
import { bytes, date, human, money, platformLabel } from "../format";
import { Quote } from "../components/evidence";
import { Empty, ErrorBox, Loading, Status, useApi, useAsync } from "../components/ui";

const KINDS = [["all", "Everything"], ["sources", "Sources"], ["content", "Content"], ["transcripts", "Transcripts"], ["comments", "Comments"],
  ["evidence", "Evidence"], ["opportunities", "Opportunities"], ["competitors", "Competitors"], ["experiments", "Experiments"],
  ["assets", "Assets"], ["reports", "Reports"], ["analyses", "Analysis history"]];

export default function Library() {
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [kind, setKind] = useState("all");
  const [aud, setAud] = useState("");
  const { data: auds } = useApi<any[]>("/api/audiences");
  useEffect(() => { const t = window.setTimeout(() => setDq(q), 300); return () => window.clearTimeout(t); }, [q]);
  const qs = new URLSearchParams({ q: dq, kind, limit: "60" });
  if (aud) qs.set("audience_id", aud);
  const { data, error, loading, reload } = useApi<any>(`/api/library?${qs}`);
  const bk = useAsync();
  const [backup, setBackup] = useState<any>(null);
  const doBackup = async () => { const r = await bk.run(() => post("/api/backup")); if (r) setBackup(r); };
  const groups = data ? Object.entries(data).filter(([, v]: any) => v.length > 0) : [];
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Research Library</h1><div className="sub">Everything you've imported and produced, searchable in one place.</div></div>
        <div className="row">
          {aud && <a className="btn" href={`/api/audiences/${aud}/export`}>Export audience (JSON)</a>}
          <button className="btn" onClick={doBackup} disabled={bk.busy}>{bk.busy ? "Backing up…" : "Back up database"}</button>
        </div>
      </div>
      {backup && <div className="notice good small mb">Backup saved to <span className="mono">{backup.path}</span> ({bytes(backup.size_bytes)}).</div>}
      <ErrorBox error={bk.error} />
      <div className="card mb">
        <div className="grid" style={{ gridTemplateColumns: "1fr 220px 260px", gap: 10 }}>
          <input type="search" placeholder="Search quotes, transcripts, comments, opportunities…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus aria-label="Search" />
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type">{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <select value={aud} onChange={(e) => setAud(e.target.value)} aria-label="Audience"><option value="">All audiences</option>{(auds || []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        </div>
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && groups.length === 0 && <div className="card"><Empty title={dq ? `Nothing matches “${dq}”` : "The library is empty"}>{dq ? "Try another word or clear filters." : "Import material into an audience to fill it."}</Empty></div>}
      <div className="stack">
        {groups.map(([g, items]: any) => (
          <div key={g} className="card">
            <div className="card-head"><h2>{human(g)}</h2><span className="badge">{items.length}</span></div>
            {g === "evidence" ? items.map((e: any) => <Quote key={e.id} q={{ ...e, evidence_id: e.id }} />) : (
              <ul className="clean small">
                {items.map((x: any) => <li key={x.id}><Item g={g} x={x} /></li>)}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Item({ g, x }: { g: string; x: any }) {
  const aud = <span className="faint"> · {x.audience_name}</span>;
  switch (g) {
    case "sources":
      return <><Link to={`/audiences/${x.audience_id}/sources?source=${x.id}`}>{x.title || x.filename || x.original_url}</Link> <Status s={x.status} /><span className="muted"> {platformLabel(x.platform)} · {x.kind} · {date(x.created_at)}</span>{aud}</>;
    case "content":
      return <><Link to={`/audiences/${x.audience_id}/sources?source=${x.source_id}&item=${x.id}`} className="strong">{x.title || "Untitled"}</Link><span className="muted"> {x.kind} · {platformLabel(x.platform)}</span>{aud}<div className="muted">…{x.snippet}…</div></>;
    case "comments":
      return <>{x.text}<div className="muted tiny"><Link to={`/audiences/${x.audience_id}/sources?source=${x.source_id}`}>source</Link> · {platformLabel(x.platform)} · {date(x.published_at)} · {x.likes ?? "—"} likes{x.is_spam ? " · spam" : ""}{x.is_duplicate ? " · duplicate" : ""}{aud}</div></>;
    case "opportunities":
      return <><Link to={`/opportunities/${x.id}`} className="strong">{x.name}</Link> <Status s={x.status} /><span className="muted"> {x.product_type} · {money(x.price, 0)} · index {Math.round(x.total_score ?? 0)}</span>{aud}</>;
    case "competitors":
      return <>{x.url ? <a href={x.url} target="_blank" rel="noreferrer noopener">{x.name}</a> : x.name}<span className="muted"> {x.price_text || ""} · {x.provenance}{x.retrieved_at ? ` ${date(x.retrieved_at)}` : ""}</span>{aud}</>;
    case "experiments":
      return <><Link to={`/validation/${x.id}`} className="strong">{x.name}</Link> <Status s={x.decision || x.status} />{aud}</>;
    case "assets":
      return <><Link to={`/opportunities/${x.opportunity_id}`}>{x.title}</Link> <Status s={x.status} /><span className="muted"> {human(x.kind)}</span>{aud}</>;
    case "reports":
      return <><a href={`/api/reports/${x.id}/html`} target="_blank" rel="noreferrer">{x.title}</a><span className="muted"> {date(x.created_at)} · </span>
        <a href={`/api/reports/${x.id}/pdf`} target="_blank" rel="noreferrer">PDF</a>{aud}</>;
    case "analyses":
      return <><Link to={`/intelligence/${x.audience_id}`}>{x.audience_name}</Link> <Status s={x.status} /><span className="muted"> {x.provider} {x.model || ""} · {date(x.started_at)} · {x.stats?.signals ?? 0} signals, {x.stats?.opportunities ?? 0} opportunities</span></>;
    default:
      return <>{x.title || x.name || x.id}</>;
  }
}
