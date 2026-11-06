import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { errText, get } from "../api";
import { isNil, money, num, pct } from "../format";

// ---------- data loading ----------

export function useApi<T = any>(path: string | null, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const seq = useRef(0);
  const reload = useCallback(async () => {
    if (!path) return;
    const my = ++seq.current;
    try {
      const d = await get<T>(path);
      if (my === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (my === seq.current) setError(errText(e));
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    setLoading(!!path);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useJobsDone(reload);
  return { data, error, loading, reload, setData };
}

// ---------- jobs polling ----------

type JobsCtx = { jobs: any[]; doneTick: number; kick: () => void };
const JobsContext = createContext<JobsCtx>({ jobs: [], doneTick: 0, kick: () => {} });

export function JobsProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<any[]>([]);
  const [doneTick, setDoneTick] = useState(0);
  const prev = useRef<Set<string>>(new Set());
  const timer = useRef<number | null>(null);
  const fast = useRef(true);

  const poll = useCallback(async () => {
    try {
      const active = await get<any[]>("/api/jobs?active=1");
      const ids = new Set(active.map((j) => j.id));
      let finished = false;
      prev.current.forEach((id) => {
        if (!ids.has(id)) finished = true;
      });
      prev.current = ids;
      setJobs(active);
      if (finished) setDoneTick((t) => t + 1);
      fast.current = active.length > 0;
    } catch {
      /* engine unreachable; keep polling slowly */
      fast.current = false;
    }
    timer.current = window.setTimeout(poll, fast.current ? 1500 : 5000);
  }, []);

  useEffect(() => {
    poll();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [poll]);

  const kick = useCallback(() => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(poll, 300);
  }, [poll]);

  return <JobsContext.Provider value={{ jobs, doneTick, kick }}>{children}</JobsContext.Provider>;
}

export const useJobs = () => useContext(JobsContext);

export function useJobsDone(fn: () => void) {
  const { doneTick } = useJobs();
  const first = useRef(true);
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    ref.current();
  }, [doneTick]);
}

// ---------- toast ----------

const ToastContext = createContext<(msg: string) => void>(() => {});
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null);
  const t = useRef<number | null>(null);
  const show = useCallback((m: string) => {
    setMsg(m);
    if (t.current) window.clearTimeout(t.current);
    t.current = window.setTimeout(() => setMsg(null), 2600);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {msg && <div className="toast" role="status">{msg}</div>}
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);

// ---------- presentational ----------

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner" /> {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="notice bad row between" role="alert">
      <span>{error}</span>
      {onRetry && (
        <button className="btn sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children, actions }: { title: string; children?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <div>{children}</div>}
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function Demo({ on }: { on: any }) {
  return on ? <span className="badge demo" title="Synthetic demonstration data">DEMO</span> : null;
}

const NM = "not measured";
export function V({ v, kind = "num", digits }: { v: any; kind?: "num" | "usd" | "pct"; digits?: number }) {
  if (isNil(v)) return <span className="faint" title={NM}>—</span>;
  if (kind === "usd") return <>{money(v, digits ?? 2)}</>;
  if (kind === "pct") return <>{pct(v, digits ?? 2)}</>;
  return <>{num(v, digits ?? 0)}</>;
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="progress" aria-valuenow={Math.round(value * 100)} role="progressbar">
      <div style={{ width: `${Math.max(3, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function Drawer({ title, onClose, children }: { title: React.ReactNode; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="drawer-head">
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button className="btn ghost sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true">
        <div className="row between mb">
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button className="btn ghost sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </>
  );
}

const STATUS_TONE: Record<string, string> = {
  ready: "good", done: "good", approved: "good", validated: "good", launched: "good", go: "good", completed: "good", active: "good",
  partial: "warn", processing: "info", running: "info", queued: "info", pending: "info", testing: "info", draft: "", continue: "info",
  revise: "warn", define: "", paused: "warn",
  failed: "bad", unsupported: "bad", rejected: "bad", stop: "bad", cancelled: "", retired: "",
};
const STATUS_LABEL: Record<string, string> = {
  ready: "Ready", partial: "Partial", processing: "Processing", pending: "Waiting", failed: "Failed", unsupported: "Not retrievable",
  queued: "Queued", running: "Running", done: "Done", cancelled: "Cancelled", proposed: "Proposed", approved: "Approved",
  testing: "Testing", validated: "Validated", rejected: "Rejected", draft: "Draft", completed: "Completed", go: "Go", revise: "Revise",
  stop: "Stop", continue: "Keep running", pending_data: "No data", define: "Needs criteria", launched: "Launched", paused: "Paused",
  retired: "Retired", active: "Active",
};
export function Status({ s }: { s: string | null | undefined }) {
  if (!s) return null;
  return <span className={`badge ${STATUS_TONE[s] ?? ""}`}>{STATUS_LABEL[s] ?? s}</span>;
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Bullets({ items, empty = "None recorded." }: { items: any[] | null | undefined; empty?: string }) {
  if (!items || !items.length) return <span className="faint">{empty}</span>;
  return (
    <ul className="bul">
      {items.map((x, i) => (
        <li key={i}>{String(x)}</li>
      ))}
    </ul>
  );
}

export function useAsync() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(errText(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

export function JobLine({ job }: { job: any }) {
  return (
    <div className="stack" style={{ minWidth: 220 }}>
      <div className="row between small">
        <span>{job.message || job.kind}</span>
        <span className="faint">{Math.round((job.progress || 0) * 100)}%</span>
      </div>
      <Progress value={job.status === "queued" ? 0.02 : job.progress || 0.02} />
    </div>
  );
}
