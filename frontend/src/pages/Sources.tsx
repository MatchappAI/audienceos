import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { del, post, upload } from "../api";
import { bytes, date, dateTime, num, platformLabel } from "../format";
import { Drawer, Empty, ErrorBox, JobLine, Loading, Status, useApi, useAsync, useJobs, useToast } from "../components/ui";
import { CHANNEL_PLATFORMS } from "./Research";

function fmtTs(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function UrlAdder({ aid, onDone }: { aid: string; onDone: () => void }) {
  const [text, setText] = useState("");
  const [voice, setVoice] = useState("creator");
  const [episodes, setEpisodes] = useState(0);
  const [checks, setChecks] = useState<Record<string, any>>({});
  const { busy, error, run } = useAsync();
  const { kick } = useJobs();
  const toast = useToast();
  const urls = Array.from(new Set(text.split(/\s+/).map((u) => u.trim()).filter(Boolean))).slice(0, 50);

  useEffect(() => {
    const t = window.setTimeout(async () => {
      const next: Record<string, any> = {};
      for (const u of urls.slice(0, 10)) {
        if (checks[u]) { next[u] = checks[u]; continue; }
        try { next[u] = await post("/api/detect", { url: u }); } catch { /* ignore */ }
      }
      setChecks(next);
    }, 450);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const submit = async () => {
    const r = await run(() => post(`/api/audiences/${aid}/sources/urls`, { urls, voice, transcribe_episodes: episodes }));
    if (r) {
      const dup = r.sources.filter((s: any) => s.duplicate).length;
      toast(`${r.sources.length - dup} link(s) queued${dup ? `, ${dup} already imported` : ""}`);
      setText("");
      kick();
      onDone();
    }
  };
  const anyFeed = Object.values(checks).some((c: any) => ["podcast", "feed", "substack"].includes(c.platform));

  return (
    <div>
      <label className="field"><span>Links — one per line (posts, videos, articles, RSS feeds, podcasts, Reddit threads)</span>
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="https://www.youtube.com/watch?v=…&#10;https://example.substack.com" /></label>
      {Object.keys(checks).length > 0 && (
        <div className="stack small mb">
          {Object.entries(checks).map(([u, c]: any) => (
            <div key={u} className="notice">
              <div className="row between"><span className="clip strong" style={{ maxWidth: 560 }}>{u}</span><span className="badge">{c.policy.label}</span></div>
              <div className="mt" style={{ marginTop: 4 }}><b>Can retrieve:</b> {c.policy.direct}</div>
              <div><b>Not available:</b> {c.policy.not_available}</div>
              {c.policy.fallback?.length > 0 && <details className="fold"><summary>Alternatives</summary><ul className="bul">{c.policy.fallback.map((f: string) => <li key={f}>{f}</li>)}</ul></details>}
            </div>
          ))}
        </div>
      )}
      <div className="row">
        <label className="row small">Whose words?
          <select value={voice} onChange={(e) => setVoice(e.target.value)} style={{ width: "auto" }}>
            <option value="creator">The creator's content</option><option value="audience">The audience's words</option>
          </select></label>
        {anyFeed && (
          <label className="row small">Transcribe latest episodes
            <select value={episodes} onChange={(e) => setEpisodes(Number(e.target.value))} style={{ width: "auto" }}>
              {[0, 1, 2, 3, 5].map((n) => <option key={n} value={n}>{n === 0 ? "None" : n}</option>)}
            </select></label>
        )}
        <span className="spacer" />
        <button className="btn primary" onClick={submit} disabled={busy || urls.length === 0}>{busy ? "Adding…" : `Retrieve ${urls.length || ""} link${urls.length === 1 ? "" : "s"}`}</button>
      </div>
      <p className="help">Requires internet. AudienceOS only uses public, permitted methods (robots.txt respected, no logins). Anything it can't get is listed with alternatives.</p>
      <ErrorBox error={error} />
    </div>
  );
}

function FileAdder({ aid, onDone }: { aid: string; onDone: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [platform, setPlatform] = useState("other");
  const [voice, setVoice] = useState("creator");
  const [over, setOver] = useState(false);
  const [results, setResults] = useState<any[] | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const { busy, error, run } = useAsync();
  const { kick } = useJobs();

  const submit = async () => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("platform", platform);
    fd.append("voice", voice);
    const r = await run(() => upload(`/api/audiences/${aid}/sources/upload`, fd));
    if (r) {
      setResults(r.files);
      setFiles([]);
      kick();
      onDone();
    }
  };

  return (
    <div>
      <div className={`dropzone ${over ? "over" : ""}`} onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); setFiles([...files, ...Array.from(e.dataTransfer.files)]); }}>
        <div className="strong" style={{ color: "var(--ink)" }}>Drop files here or click to choose</div>
        <div className="small">Text, Markdown, HTML, PDF, DOCX, CSV, JSON (comment exports, analytics), audio (MP3, WAV, M4A), video (MP4, MOV), images · up to 1 GB each</div>
        <input ref={input} type="file" multiple hidden onChange={(e) => { setFiles([...files, ...Array.from(e.target.files || [])]); e.target.value = ""; }} />
      </div>
      {files.length > 0 && (
        <ul className="clean small mt">
          {files.map((f, i) => (
            <li key={i} className="row between"><span>{f.name} <span className="faint">{bytes(f.size)}</span></span>
              <button className="btn ghost sm" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Remove</button></li>
          ))}
        </ul>
      )}
      <div className="row mt">
        <label className="row small">Platform
          <select value={platform} onChange={(e) => setPlatform(e.target.value)} style={{ width: "auto" }}>
            {CHANNEL_PLATFORMS.map((p) => <option key={p} value={p}>{platformLabel(p)}</option>)}
          </select></label>
        <label className="row small">Whose words?
          <select value={voice} onChange={(e) => setVoice(e.target.value)} style={{ width: "auto" }}>
            <option value="creator">The creator's content</option><option value="audience">The audience's words (surveys, emails, reviews)</option>
          </select></label>
        <span className="spacer" />
        <button className="btn primary" onClick={submit} disabled={busy || files.length === 0}>{busy ? "Uploading…" : `Import ${files.length || ""} file${files.length === 1 ? "" : "s"}`}</button>
      </div>
      <p className="help">Files stay on this Mac. Audio and video are transcribed locally. Comment files (CSV/JSON) are always treated as the audience's words.</p>
      <ErrorBox error={error} />
      {results && (
        <ul className="clean small mt">
          {results.map((r, i) => (
            <li key={i}>{r.filename}: {r.error ? <span style={{ color: "var(--bad)" }}>{r.error}</span> : r.duplicate ? <span className="muted">already imported</span> : <span style={{ color: "var(--good)" }}>queued</span>}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TextAdder({ aid, onDone }: { aid: string; onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [platform, setPlatform] = useState("other");
  const [asComments, setAsComments] = useState(false);
  const [voice, setVoice] = useState("creator");
  const { busy, error, run } = useAsync();
  const { kick } = useJobs();
  const toast = useToast();
  const submit = async () => {
    const r = await run(() => post(`/api/audiences/${aid}/sources/text`, { title: title || null, text, platform, as_comments: asComments, voice }));
    if (r) {
      toast(r.duplicate ? "This text was already imported" : "Text added");
      setText(""); setTitle(""); kick(); onDone();
    }
  };
  return (
    <div>
      <div className="grid g2">
        <label className="field"><span>Title</span><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Transcript — Q&A livestream" /></label>
        <label className="field"><span>Platform</span>
          <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
            {CHANNEL_PLATFORMS.map((p) => <option key={p} value={p}>{platformLabel(p)}</option>)}
          </select></label>
      </div>
      <label className="field"><span>Text</span><textarea rows={7} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a transcript, caption, newsletter, DMs you're allowed to use, or comments…" /></label>
      <div className="row">
        <label className="check small"><input type="checkbox" checked={asComments} onChange={(e) => setAsComments(e.target.checked)} /><span>Each line is a separate audience comment</span></label>
        {!asComments && (
          <label className="row small">Whose words?
            <select value={voice} onChange={(e) => setVoice(e.target.value)} style={{ width: "auto" }}>
              <option value="creator">The creator's</option><option value="audience">The audience's</option>
            </select></label>
        )}
        <span className="spacer" />
        <button className="btn primary" onClick={submit} disabled={busy || !text.trim()}>{busy ? "Adding…" : "Add text"}</button>
      </div>
      <ErrorBox error={error} />
    </div>
  );
}

function ContentDetail({ cid }: { cid: string }) {
  const { data: c, loading, error } = useApi<any>(`/api/content/${cid}`);
  if (loading) return <Loading />;
  if (error || !c) return <ErrorBox error={error} />;
  const tr = c.transcripts?.[0];
  return (
    <div className="stack">
      <h3>{c.title || "Content"}</h3>
      <div className="small muted">{c.kind} · {num(c.word_count)} words · {date(c.published_at)} {c.url && <a href={c.url} target="_blank" rel="noreferrer noopener">open</a>}</div>
      {c.metrics?.length > 0 && (
        <table className="t small"><tbody>{c.metrics.map((m: any, i: number) => <tr key={i}><td>{m.metric}</td><td className="num">{num(m.value)}</td><td className="muted">{m.source_note}</td></tr>)}</tbody></table>
      )}
      {c.frames?.length > 0 && (
        <div className="grid g3">
          {c.frames.map((f: any) => (
            <figure key={f.id} style={{ margin: 0 }}>
              <img src={`/api/frames/${f.id}/image`} alt={`Frame at ${fmtTs(f.timestamp_s)}`} style={{ width: "100%", borderRadius: 6, border: "1px solid var(--line)" }} />
              <figcaption className="tiny muted">{fmtTs(f.timestamp_s)}{f.description ? ` — ${f.description} (${f.described_by})` : " — not analyzed"}</figcaption>
            </figure>
          ))}
        </div>
      )}
      {tr ? (
        <div>
          <div className="small muted mb">Transcript · {tr.engine} · {tr.language}</div>
          <div className="card small" style={{ maxHeight: 380, overflow: "auto", padding: 12 }}>
            {(tr.segments || []).map((s: any, i: number) => (
              <div key={i} className="row top" style={{ gap: 10, flexWrap: "nowrap" }}><span className="mono faint">{fmtTs(s.start)}</span><span>{s.text}</span></div>
            ))}
          </div>
        </div>
      ) : (
        <div className="card small prewrap" style={{ maxHeight: 380, overflow: "auto", padding: 12 }}>{c.text || <span className="faint">No text.</span>}</div>
      )}
    </div>
  );
}

function SourceDrawer({ sid, initialItem, onClose, onChanged }: { sid: string; initialItem?: string | null; onClose: () => void; onChanged: () => void }) {
  const { data: s, loading, error, reload } = useApi<any>(`/api/sources/${sid}`);
  const [item, setItem] = useState<string | null>(initialItem || null);
  const act = useAsync();
  const { kick } = useJobs();
  const reprocess = async () => { if (await act.run(() => post(`/api/sources/${sid}/reprocess`))) { kick(); reload(); onChanged(); } };
  const remove = async () => {
    if (!window.confirm("Delete this source and everything extracted from it?")) return;
    if (await act.run(() => del(`/api/sources/${sid}`))) { onChanged(); onClose(); }
  };
  return (
    <Drawer title={s ? s.title || s.filename || s.original_url : "Source"} onClose={onClose}>
      {loading && <Loading />}
      <ErrorBox error={error || act.error} />
      {s && !item && (
        <div className="stack">
          <div className="row"><Status s={s.status} /><span className="small muted">{platformLabel(s.platform)} · {s.voice === "audience" ? "audience's words" : "creator's content"} · {s.retrieval_method || s.kind}</span>
            <span className="spacer" />
            {s.kind !== "text" && <button className="btn sm" onClick={reprocess} disabled={act.busy}>Reprocess</button>}
            <button className="btn sm danger" onClick={remove} disabled={act.busy}>Delete</button></div>
          {s.original_url && <a className="small" href={s.original_url} target="_blank" rel="noreferrer noopener">{s.original_url}</a>}
          <SourceFindings s={s} />
          {s.comment_stats?.total > 0 && (
            <div className="small muted">{num(s.comment_stats.total)} comments · {num(s.comment_stats.duplicates)} duplicates · {num(s.comment_stats.spam)} likely spam · {num(s.comment_stats.authors)} distinct (hashed) authors</div>
          )}
          {s.items.length > 0 && (
            <div>
              <h3>Content ({s.items.length})</h3>
              <ul className="clean small">
                {s.items.map((it: any) => (
                  <li key={it.id}><button className="linkbtn strong" onClick={() => setItem(it.id)}>{it.title || "Untitled"}</button>
                    <span className="muted"> · {it.kind} · {num(it.word_count)} words{it.published_at ? ` · ${date(it.published_at)}` : ""}</span>
                    <div className="muted clip">{it.preview}</div></li>
                ))}
              </ul>
            </div>
          )}
          {s.comments.length > 0 && (
            <div>
              <h3>Comments (top {s.comments.length} by likes)</h3>
              <ul className="clean small">
                {s.comments.map((c: any) => (
                  <li key={c.id} style={{ opacity: c.is_spam || c.is_duplicate ? 0.6 : 1 }}>
                    {c.text}
                    <div className="row tiny muted" style={{ gap: 8 }}>{date(c.published_at)} · {c.likes ?? "—"} likes
                      {c.is_duplicate ? <span className="badge">duplicate</span> : null}
                      {c.is_spam ? <span className="badge bad">spam: {c.spam_reason}</span> : null}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {item && (
        <div>
          <button className="btn ghost sm mb" onClick={() => setItem(null)}>← Back to source</button>
          <ContentDetail cid={item} />
        </div>
      )}
    </Drawer>
  );
}

export function SourceFindings({ s }: { s: any }) {
  return (
    <div className="grid g2 small">
      <div><div className="muted strong tiny">OBTAINED</div>{s.obtained?.length ? <ul className="bul">{s.obtained.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul> : <span className="faint">Nothing yet</span>}</div>
      <div><div className="muted strong tiny">NOT AVAILABLE</div>{s.missing?.length ? <ul className="bul">{s.missing.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul> : <span className="faint">—</span>}</div>
      {s.alternatives?.length > 0 && (
        <div style={{ gridColumn: "1 / -1" }} className="notice info"><b>What you can do instead</b><ul className="bul">{s.alternatives.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>
      )}
      {s.status_detail && s.status === "failed" && <div style={{ gridColumn: "1 / -1" }} className="notice bad">{s.status_detail}</div>}
    </div>
  );
}

export default function SourcesTab({ audience, reloadAudience }: { audience: any; reloadAudience: () => void }) {
  const aid = audience.id;
  const { data, error, loading, reload } = useApi<any[]>(`/api/audiences/${aid}/sources`);
  const [mode, setMode] = useState<"files" | "urls" | "text">("files");
  // Deep links from the Library: ?source=<id>[&item=<content id>] opens that source (and item) directly.
  const [params, setParams] = useSearchParams();
  const [open, setOpenState] = useState<string | null>(params.get("source"));
  const initialItem = params.get("item");
  const setOpen = (v: string | null) => {
    setOpenState(v);
    if (!v && (params.get("source") || params.get("item"))) { params.delete("source"); params.delete("item"); setParams(params, { replace: true }); }
  };
  const { jobs } = useJobs();
  const refresh = () => { reload(); reloadAudience(); };

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head">
          <h2>Add material</h2>
          <div className="seg" role="tablist">
            <button className={mode === "files" ? "on" : ""} onClick={() => setMode("files")}>Upload files</button>
            <button className={mode === "urls" ? "on" : ""} onClick={() => setMode("urls")}>Add links</button>
            <button className={mode === "text" ? "on" : ""} onClick={() => setMode("text")}>Paste text</button>
          </div>
        </div>
        {mode === "files" && <FileAdder aid={aid} onDone={refresh} />}
        {mode === "urls" && <UrlAdder aid={aid} onDone={refresh} />}
        {mode === "text" && <TextAdder aid={aid} onDone={refresh} />}
      </div>

      {data && data.length > 0 && (() => {
        const busy = data.filter((s) => s.status === "pending" || s.status === "processing").length;
        const ready = data.filter((s) => s.status === "ready" || s.status === "partial").length;
        if (busy) return <div className="notice info small">{busy} source{busy === 1 ? " is" : "s are"} still processing — you can run the analysis once {busy === 1 ? "it finishes" : "they finish"}.</div>;
        if (ready && !audience.last_analyzed_at) return <div className="notice good row between"><span><b>{ready} source{ready === 1 ? "" : "s"} ready.</b> Next: run the analysis to find what this audience struggles with and would pay for.</span><Link className="btn primary sm" to={`/audiences/${aid}/problems`}>Run analysis →</Link></div>;
        return null;
      })()}

      <div className="card" style={{ padding: 0 }}>
        <div className="card-head" style={{ padding: "16px 20px 0" }}><h2>Sources</h2><span className="small muted">{data?.length ?? 0} imported</span></div>
        {loading && <Loading />}
        <ErrorBox error={error} onRetry={reload} />
        {data && data.length === 0 && <Empty title="Nothing imported yet">Upload a comment export, a video, a newsletter or paste a transcript to begin.</Empty>}
        {data && data.length > 0 && (
          <table className="t">
            <thead><tr><th style={{ paddingLeft: 20 }}>Source</th><th>Status</th><th>Obtained</th><th>Missing</th><th>Added</th></tr></thead>
            <tbody>
              {data.map((s) => {
                const job = jobs.find((j) => j.ref_id === s.id);
                return (
                  <tr key={s.id} className="click" onClick={() => setOpen(s.id)}>
                    <td style={{ paddingLeft: 20, maxWidth: 300 }}>
                      <div className="strong clip">{s.title || s.filename || s.original_url}</div>
                      <div className="small muted">{platformLabel(s.platform)} · {s.kind}{s.voice === "audience" ? " · audience's words" : ""}{s.size_bytes ? ` · ${bytes(s.size_bytes)}` : ""}</div>
                    </td>
                    <td style={{ minWidth: 150 }}>
                      {job ? <JobLine job={job} /> : <Status s={s.status} />}
                      {s.status === "failed" && s.job_error && !job && <div className="tiny" style={{ color: "var(--bad)" }}>{String(s.job_error).slice(0, 140)}</div>}
                    </td>
                    <td className="small">{(s.obtained || []).slice(0, 2).join("; ") || <span className="faint">—</span>}</td>
                    <td className="small muted">{(s.missing || []).slice(0, 1).join("; ") || "—"}{(s.missing || []).length > 1 ? ` (+${s.missing.length - 1})` : ""}</td>
                    <td className="small muted" style={{ whiteSpace: "nowrap" }}>{dateTime(s.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      {open && <SourceDrawer sid={open} initialItem={open === params.get("source") ? initialItem : null} onClose={() => setOpen(null)} onChanged={refresh} />}
    </div>
  );
}
