import React, { createContext, useContext, useState } from "react";
import { Drawer, ErrorBox, Loading, useApi } from "./ui";
import { date, INTENT_LABEL, platformLabel, TYPE_LABEL } from "../format";

const Ctx = createContext<(id: string) => void>(() => {});
export const useEvidence = () => useContext(Ctx);

export function EvidenceProvider({ children }: { children: React.ReactNode }) {
  const [id, setId] = useState<string | null>(null);
  return (
    <Ctx.Provider value={setId}>
      {children}
      {id && <EvidenceDrawer id={id} onClose={() => setId(null)} />}
    </Ctx.Provider>
  );
}

function Highlight({ text, quote }: { text: string; quote: string }) {
  const i = text.indexOf(quote);
  if (i < 0) {
    const j = text.indexOf(quote.slice(0, 60));
    if (j < 0) return <>{text}</>;
    return (
      <>
        {text.slice(0, j)}
        <mark>{text.slice(j, j + quote.length)}</mark>
        {text.slice(j + quote.length)}
      </>
    );
  }
  return (
    <>
      {text.slice(0, i)}
      <mark>{quote}</mark>
      {text.slice(i + quote.length)}
    </>
  );
}

function EvidenceDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: e, error, loading } = useApi<any>(`/api/evidence/${id}`);
  return (
    <Drawer title="Source evidence" onClose={onClose}>
      {loading && <Loading />}
      <ErrorBox error={error} />
      {e && (
        <div className="stack">
          <div className="notice info">
            <div className="tiny muted strong" style={{ marginBottom: 4 }}>
              VERBATIM QUOTE {e.verified ? "· verified against the source" : ""}
            </div>
            <div style={{ fontSize: 15 }}>“{e.quote}”</div>
            {e.locator && <div className="small muted mt">Location: {e.locator}</div>}
          </div>
          {e.signals?.length > 0 && (
            <div>
              <h3>How the analysis read it</h3>
              <ul className="clean small">
                {e.signals.map((s: any, i: number) => (
                  <li key={i}>
                    <span className="badge">{TYPE_LABEL[s.signal_type] || s.signal_type}</span>{" "}
                    <span className="badge info">{INTENT_LABEL[s.intent_level] || s.intent_level}</span>{" "}
                    {s.cluster && <span className="muted">in “{s.cluster}”</span>}
                    <div className="muted mt" style={{ marginTop: 4 }}>
                      AI summary (interpretation): {s.summary}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {e.source && (
            <div>
              <h3>Source</h3>
              <dl className="kv small">
                <dt>Title</dt>
                <dd>{e.source.title || e.source.filename || "—"}</dd>
                <dt>Platform</dt>
                <dd>{platformLabel(e.source.platform)}</dd>
                <dt>Whose words</dt>
                <dd>{e.source.voice === "audience" ? "Audience" : "Creator"}</dd>
                {e.source.original_url && (
                  <>
                    <dt>Link</dt>
                    <dd>
                      <a href={e.source.original_url} target="_blank" rel="noreferrer noopener">
                        {e.source.original_url}
                      </a>
                    </dd>
                  </>
                )}
                <dt>Retrieved</dt>
                <dd>
                  {date(e.source.retrieved_at)} · {e.source.retrieval_method || "—"}
                </dd>
              </dl>
            </div>
          )}
          {e.comment && (
            <div>
              <h3>Full comment</h3>
              <div className="card" style={{ padding: 12 }}>
                <Highlight text={e.comment.text} quote={e.quote} />
                <div className="small muted mt">
                  {platformLabel(e.comment.platform)} · {date(e.comment.published_at)} · {e.comment.likes ?? "—"} likes
                  {e.comment.parent_ref && <> · on {e.comment.parent_ref}</>}
                </div>
              </div>
            </div>
          )}
          {e.content_item && (
            <div>
              <h3>In context — {e.content_item.title || "content"}</h3>
              <div className="card prewrap small" style={{ padding: 12, maxHeight: 360, overflow: "auto" }}>
                {e.content_item.context_start > 0 && "… "}
                <Highlight text={e.content_item.context || ""} quote={e.quote} />
                {" …"}
              </div>
              {e.content_item.url && (
                <a className="small" href={e.content_item.url} target="_blank" rel="noreferrer noopener">
                  Open original
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}

export function Quote({ q, showCluster }: { q: any; showCluster?: string }) {
  const open = useEvidence();
  return (
    <div className="quote" onClick={() => open(q.evidence_id || q.id)} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && open(q.evidence_id || q.id)}>
      <div className="q">“{q.quote}”</div>
      <div className="meta">
        {q.intent_level && <span className="badge info">{INTENT_LABEL[q.intent_level] || q.intent_level}</span>}
        {q.signal_type && <span>{TYPE_LABEL[q.signal_type]}</span>}
        <span>{platformLabel(q.platform)}</span>
        {(q.source_title || q.item_title) && <span className="clip" style={{ maxWidth: 260 }}>{q.source_title || q.item_title}</span>}
        {q.locator && <span>{q.locator}</span>}
        {q.likes ? <span>{q.likes} likes</span> : null}
        {showCluster && <span>{showCluster}</span>}
      </div>
    </div>
  );
}
