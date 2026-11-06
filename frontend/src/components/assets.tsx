import { useEffect, useState } from "react";
import { del, get, patch, post } from "../api";
import { dateTime, human } from "../format";
import { Drawer, Empty, ErrorBox, JobLine, Loading, Modal, Status, useApi, useAsync, useJobs, useToast } from "./ui";

export function GenerateAssetModal({ opportunityId, experimentId, onClose, onStarted }: {
  opportunityId: string; experimentId?: string; onClose: () => void; onStarted: (jobId: string) => void;
}) {
  const { data: kinds } = useApi<Record<string, string>>("/api/asset-kinds");
  const [kind, setKind] = useState("offer");
  const [instr, setInstr] = useState("");
  const { busy, error, run } = useAsync();
  const { kick } = useJobs();
  const go = async () => {
    const r = await run(() => post("/api/assets/generate", { opportunity_id: opportunityId, experiment_id: experimentId || null, kind, instructions: instr || null }));
    if (r) { kick(); onStarted(r.job_id); onClose(); }
  };
  return (
    <Modal title="Draft an asset" onClose={onClose}>
      <label className="field"><span>What to create</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {kinds && Object.entries(kinds).map(([k, v]) => <option key={k} value={k}>{human(k)} — {v}</option>)}
        </select></label>
      <label className="field"><span>Direction (optional)</span>
        <textarea rows={3} value={instr} onChange={(e) => setInstr(e.target.value)} placeholder="e.g. warm, plain-spoken tone; mention the weekday schedule" /></label>
      <p className="small muted">Drafts use the audience's own words for context, then go through a claim review. Nothing is published — every draft needs your approval.</p>
      <ErrorBox error={error} />
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={go} disabled={busy}>{busy ? "Starting…" : "Draft it"}</button>
      </div>
    </Modal>
  );
}

function AssetDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { data: a, loading, error, reload } = useApi<any>(`/api/assets/${id}`);
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState("");
  const [view, setView] = useState<"preview" | "text">("preview");
  const [stamp, setStamp] = useState(0);
  const [checked, setChecked] = useState(false);
  const act = useAsync();
  const toast = useToast();
  useEffect(() => { if (a) setContent(a.content); }, [a]);
  const save = async () => { if (await act.run(() => patch(`/api/assets/${id}`, { content }))) { setEditing(false); setStamp(Date.now()); reload(); onChanged(); toast("Saved — needs re-approval"); } };
  const approve = async (v: boolean) => { if (await act.run(() => post(`/api/assets/${id}/approve`, { approved: v }))) { setStamp(Date.now()); reload(); onChanged(); } };
  const remove = async () => { if (window.confirm("Delete this draft?") && (await act.run(() => del(`/api/assets/${id}`)))) { onChanged(); onClose(); } };
  const flags = (Array.isArray(a?.review?.flags) ? a.review.flags : []).filter((f: any) => f && typeof f === "object");
  return (
    <Drawer title={a?.title || "Asset"} onClose={onClose}>
      {loading && <Loading />}
      <ErrorBox error={error || act.error} />
      {a && (
        <div className="stack">
          <div className="row"><Status s={a.status} /><span className="small muted">{human(a.kind)} · {dateTime(a.created_at)}</span><span className="spacer" />
            {a.status === "approved" ? <button className="btn sm" onClick={() => approve(false)}>Unapprove</button>
              : <>
                {flags.length > 0 && <label className="check small" style={{ margin: 0 }}><input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} /><span>I fixed or checked the flagged claim{flags.length > 1 ? "s" : ""}</span></label>}
                <button className="btn sm accent" onClick={() => approve(true)} disabled={act.busy || (flags.length > 0 && !checked)}
                  title={flags.length > 0 && !checked ? "Tick the box once you've fixed or checked the flagged claims" : undefined}>Approve</button>
              </>}
            <button className="btn ghost sm danger" onClick={remove}>Delete</button></div>
          {flags.length > 0 ? (
            <div className="notice warn small">
              <b>{flags.length} claim{flags.length > 1 ? "s" : ""} to check before approving</b>
              <ul className="bul">{flags.map((f: any, i: number) => <li key={i}><b>{f?.problem || "Check this claim"}</b>{f?.claim ? <> — “{String(f.claim)}”</> : null} <span className="muted">({f?.by || "review"}{f?.suggestion ? `; ${f.suggestion}` : ""})</span></li>)}</ul>
            </div>
          ) : <div className="notice good small">No risky claims flagged. Still read it before approving.</div>}
          {a.review?.overall && <div className="small muted">Reviewer: {a.review.overall}</div>}
          <div className="row">
            <div className="seg"><button className={view === "preview" ? "on" : ""} onClick={() => setView("preview")}>Preview</button>
              <button className={view === "text" ? "on" : ""} onClick={() => setView("text")}>Text</button></div>
            <span className="spacer" />
            <a className="btn ghost sm" href={`/api/assets/${id}/export?format=md`}>.md</a>
            <a className="btn ghost sm" href={`/api/assets/${id}/export?format=html`}>.html</a>
            <a className="btn ghost sm" href={`/api/assets/${id}/export?format=docx`}>.docx</a>
            <a className="btn ghost sm" href={`/api/assets/${id}/preview`} target="_blank" rel="noreferrer">Open ↗</a>
          </div>
          {view === "preview" && <iframe className="preview" title="Preview" src={`/api/assets/${id}/preview?t=${stamp}`} sandbox={a.kind === "calculator" ? "allow-scripts" : ""} />}
          {view === "text" && (editing ? (
            <>
              <textarea rows={22} value={content} onChange={(e) => setContent(e.target.value)} className="mono" />
              <div className="row"><button className="btn primary" onClick={save} disabled={act.busy}>Save</button><button className="btn" onClick={() => { setEditing(false); setContent(a.content); }}>Cancel</button>
                <span className="small muted">Editing resets approval.</span></div>
            </>
          ) : (
            <>
              <div className="card small" style={{ maxHeight: 460, overflow: "auto" }} dangerouslySetInnerHTML={{ __html: a.html }} />
              {a.kind !== "landing_page" && a.kind !== "calculator" && <button className="btn sm" onClick={() => setEditing(true)}>Edit text</button>}
            </>
          ))}
        </div>
      )}
    </Drawer>
  );
}

export function AssetPanel({ opportunityId, experimentId, assets, reload }: { opportunityId: string; experimentId?: string; assets: any[]; reload: () => void }) {
  const [gen, setGen] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobErr, setJobErr] = useState<string | null>(null);
  const { jobs } = useJobs();
  const running = jobId ? jobs.find((j) => j.id === jobId) : null;
  useEffect(() => {
    if (jobId && !running) {
      get(`/api/jobs/${jobId}`).then((j: any) => {
        if (j.status === "failed") setJobErr(j.error);
        if (j.status === "done") { reload(); if (j.ref_id) setOpen(j.ref_id); }
        if (j.status !== "queued" && j.status !== "running") setJobId(null);
      }).catch(() => setJobId(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, running]);
  return (
    <div className="card">
      <div className="card-head">
        <h2>Marketing & product assets</h2>
        {running ? <JobLine job={running} /> : <button className="btn sm" onClick={() => { setJobErr(null); setGen(true); }}>+ Draft asset</button>}
      </div>
      {jobErr && <ErrorBox error={`Drafting failed: ${jobErr}`} />}
      {assets.length === 0 ? <Empty title="No drafts yet">Draft a test offer, landing page, newsletter promo, social scripts, sample, outline, checklist, calculator and more.</Empty> : (
        <ul className="clean">
          {assets.map((x) => (
            <li key={x.id} className="row between"><button className="linkbtn" onClick={() => setOpen(x.id)}>{x.title}</button>
              <span className="row small"><span className="muted">{human(x.kind)}</span><Status s={x.status} /></span></li>
          ))}
        </ul>
      )}
      {gen && <GenerateAssetModal opportunityId={opportunityId} experimentId={experimentId} onClose={() => setGen(false)} onStarted={setJobId} />}
      {open && <AssetDrawer id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  );
}
