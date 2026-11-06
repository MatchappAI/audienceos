import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post } from "../api";
import { compact, date, num, platformLabel } from "../format";
import { Demo, Empty, ErrorBox, Loading, Modal, useApi, useAsync } from "../components/ui";

export const CHANNEL_PLATFORMS = ["youtube", "tiktok", "instagram", "facebook", "x", "linkedin", "reddit", "substack",
  "newsletter", "podcast", "web", "community", "other"];

type Ch = { platform: string; handle: string; url: string; follower_count: string };

export function NewAudienceModal({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const [org, setOrg] = useState("");
  const [kind, setKind] = useState("creator");
  const [name, setName] = useState("");
  const [niche, setNiche] = useState("");
  const [desc, setDesc] = useState("");
  const [chs, setChs] = useState<Ch[]>([{ platform: "instagram", handle: "", url: "", follower_count: "" }]);
  const { busy, error, run } = useAsync();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = {
      org_name: org, org_kind: kind, name: name || undefined, niche: niche || undefined, description: desc || undefined,
      channels: chs.filter((c) => c.handle || c.url || c.follower_count).map((c) => ({
        platform: c.platform, handle: c.handle || null, url: c.url || null,
        follower_count: c.follower_count ? Number(c.follower_count.replace(/[, ]/g, "")) : null,
      })),
    };
    const r = await run(() => post("/api/audiences", body));
    if (r) nav(`/audiences/${r.id}/sources`);
  };

  const setCh = (i: number, k: keyof Ch, v: string) => setChs(chs.map((c, j) => (j === i ? { ...c, [k]: v } : c)));

  return (
    <Modal title="New creator or business" onClose={onClose}>
      <form onSubmit={submit}>
        <div className="grid g2">
          <label className="field"><span>Creator or business name *</span>
            <input value={org} onChange={(e) => setOrg(e.target.value)} required autoFocus placeholder="e.g. Maya Chen" /></label>
          <label className="field"><span>Type</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="creator">Creator</option><option value="business">Business</option>
              <option value="publisher">Publisher</option><option value="community">Community</option><option value="other">Other</option>
            </select></label>
        </div>
        <div className="grid g2">
          <label className="field"><span>Audience name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Defaults to “<name> audience”" /></label>
          <label className="field"><span>Niche</span>
            <input value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="e.g. Sourdough home baking" /></label>
        </div>
        <label className="field"><span>Notes</span>
          <textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} style={{ minHeight: 50 }} /></label>
        <h3 className="mt">Channels</h3>
        <p className="small muted">Add each platform where this audience follows them. Follower counts you enter are labeled “entered by you”.</p>
        {chs.map((c, i) => (
          <div key={i} className="grid" style={{ gridTemplateColumns: "130px 1fr 1fr 110px 28px", gap: 8, marginBottom: 8 }}>
            <select value={c.platform} onChange={(e) => setCh(i, "platform", e.target.value)} aria-label="Platform">
              {CHANNEL_PLATFORMS.map((p) => <option key={p} value={p}>{platformLabel(p)}</option>)}
            </select>
            <input placeholder="@handle" value={c.handle} onChange={(e) => setCh(i, "handle", e.target.value)} aria-label="Handle" />
            <input placeholder="Profile URL" value={c.url} onChange={(e) => setCh(i, "url", e.target.value)} aria-label="URL" />
            <input placeholder="Followers" inputMode="numeric" value={c.follower_count} onChange={(e) => setCh(i, "follower_count", e.target.value)} aria-label="Followers" />
            <button type="button" className="btn ghost sm" onClick={() => setChs(chs.filter((_, j) => j !== i))} aria-label="Remove channel">✕</button>
          </div>
        ))}
        <button type="button" className="btn sm" onClick={() => setChs([...chs, { platform: "youtube", handle: "", url: "", follower_count: "" }])}>
          + Add channel
        </button>
        <ErrorBox error={error} />
        <div className="row mt2" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy || !org.trim()}>{busy ? "Creating…" : "Create and add content"}</button>
        </div>
      </form>
    </Modal>
  );
}

export default function Research() {
  const [params, setParams] = useSearchParams();
  const showNew = params.get("new") === "1";
  const { data, error, loading, reload } = useApi<any[]>("/api/audiences");
  const nav = useNavigate();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Audience Research</h1>
          <div className="sub">Creators and businesses you're researching, each with one or more channels.</div>
        </div>
        <button className="btn primary" onClick={() => setParams({ new: "1" })}>New creator or business</button>
      </div>
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.length === 0 && (
        <div className="card">
          <Empty title="No audiences yet" actions={<button className="btn primary" onClick={() => setParams({ new: "1" })}>Add a creator</button>}>
            Start by adding a creator or business, then import links, files, transcripts or comment exports.
          </Empty>
        </div>
      )}
      {data && data.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="t">
            <thead>
              <tr>
                <th style={{ paddingLeft: 20 }}>Audience</th><th>Platforms</th><th className="num">Audience size</th>
                <th className="num">Sources</th><th className="num">Comments</th><th className="num">Opportunities</th>
                <th className="num">Experiments</th><th>Last analyzed</th>
              </tr>
            </thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id} className="click" onClick={() => nav(`/audiences/${a.id}`)}>
                  <td style={{ paddingLeft: 20 }}>
                    <div className="row" style={{ gap: 6 }}><Link to={`/audiences/${a.id}`} className="strong">{a.name}</Link> <Demo on={a.is_demo} /></div>
                    <div className="small muted">{a.org_name}{a.niche ? ` · ${a.niche}` : ""}</div>
                  </td>
                  <td className="small">{a.platforms ? String(a.platforms).split(",").map(platformLabel).join(", ") : <span className="faint">—</span>}</td>
                  <td className="num">{a.audience_size ? compact(a.audience_size) : <span className="faint" title="not entered">—</span>}</td>
                  <td className="num">{num(a.source_count)}</td>
                  <td className="num">{num(a.comment_count)}</td>
                  <td className="num">{num(a.opportunity_count)}</td>
                  <td className="num">{num(a.experiment_count)}</td>
                  <td className="small">{a.last_analyzed_at ? date(a.last_analyzed_at) : <span className="faint">Not yet</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {showNew && <NewAudienceModal onClose={() => setParams({})} />}
    </div>
  );
}
