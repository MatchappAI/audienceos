import { useEffect, useState } from "react";
import { del, put, post } from "../api";
import { applyTheme, getTheme } from "../App";
import { ErrorBox, JobLine, Loading, useApi, useAsync, useJobs, useJobsDone, useToast } from "../components/ui";

const KEYS: [string, string, string][] = [
  ["anthropic_api_key", "Anthropic (Claude) API key", "Optional higher-quality analysis. Data is sent to Anthropic only when external AI is allowed and you confirm each run. Paid usage."],
  ["openai_api_key", "OpenAI API key", "Optional alternative external model. Paid usage."],
  ["youtube_api_key", "YouTube Data API key", "Free from Google Cloud. Imports public comments and view/like counts for YouTube links."],
  ["brave_api_key", "Brave Search API key", "Free tier available. Enables automated competitor search when web research is on."],
  ["stripe_api_key", "Stripe restricted key (read-only)", "Pulls orders for products sold through Stripe Payment Links. Create a restricted key with read access to Checkout Sessions, Payment Intents, Charges and Balance transactions. Sent only to api.stripe.com."],
  ["gumroad_access_token", "Gumroad access token", "Pulls orders for Gumroad products. Gumroad → Settings → Advanced → Applications → generate an access token. Sent only to api.gumroad.com."],
  ["shopify_access_token", "Shopify Admin API token", "Pulls orders for Shopify products. Shopify admin → Settings → Apps → Develop apps → create an app with only the read_orders scope → install → copy the Admin API token. Sent only to your *.myshopify.com store."],
  ["lemonsqueezy_api_key", "Lemon Squeezy API key", "Pulls orders for Lemon Squeezy products. Lemon Squeezy → Settings → API. Sent only to api.lemonsqueezy.com."],
];

function Toggle({ on, onChange, label, help }: { on: boolean; onChange: (v: boolean) => void; label: string; help?: string }) {
  return (
    <label className="check"><input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
      <span><b>{label}</b>{help && <div className="small muted">{help}</div>}</span></label>
  );
}

function SecretRow({ name, label, help, saved, onSaved }: { name: string; label: string; help: string; saved: boolean; onSaved: () => void }) {
  const [v, setV] = useState("");
  const act = useAsync();
  const toast = useToast();
  const save = async (value: string | null) => { if (await act.run(() => put(`/api/secrets/${name}`, { value }))) { setV(""); toast(value ? "Saved to Keychain" : "Removed"); onSaved(); } };
  return (
    <div className="mb">
      <div className="row between"><b className="small">{label}</b>{saved ? <span className="badge good">saved in Keychain</span> : <span className="badge">not set</span>}</div>
      <div className="small muted">{help}</div>
      <div className="row mt" style={{ marginTop: 6 }}>
        <input type="password" autoComplete="off" value={v} onChange={(e) => setV(e.target.value)} placeholder={saved ? "Enter a new key to replace" : "Paste key"} style={{ maxWidth: 420 }} aria-label={label} />
        <button className="btn sm" onClick={() => save(v.trim())} disabled={!v.trim() || act.busy}>Save</button>
        {saved && <button className="btn ghost sm danger" onClick={() => save(null)} disabled={act.busy}>Remove</button>}
      </div>
      <ErrorBox error={act.error} />
    </div>
  );
}

// Model families that accept images. Text-only models (e.g. qwen2.5:7b) can't describe video frames.
const VISION_RX = /(vl|llava|vision|moondream|minicpm-v|bakllava|gemma3|granite3\.2-vision|mistral-small3\.1)/i;

function ModelPresets({ onDone }: { onDone: () => void }) {
  const { data, reload } = useApi<any>("/api/models/presets");
  const { jobs, kick } = useJobs();
  const act = useAsync();
  const toast = useToast();
  useJobsDone(() => { reload(); onDone(); });
  if (!data) return null;
  const pull = async (p: any) => {
    const r = await act.run(() => post("/api/models/pull", { model: p.model, purpose: p.purpose }));
    if (r) { toast(`Downloading ${p.model}`); kick(); reload(); }
  };
  return (
    <div className="card">
      <h2>Optional local models</h2>
      <p className="small muted">One click each. They run on this Mac; downloading needs the internet once.</p>
      {!data.engine_running && <div className="notice warn small">The local AI engine isn't running. Restart AudienceOS with the launcher to download models.</div>}
      {data.presets.map((p: any) => {
        const job = jobs.find((j: any) => j.id === p.job_id) || (p.job_id ? { message: `Downloading ${p.model}`, progress: 0, status: "queued" } : null);
        return (
          <div key={p.model} className="row between mb" style={{ alignItems: "flex-start", gap: 12 }}>
            <div><b className="small">{p.title}</b> <span className="mono tiny faint">{p.model} · {p.size}</span>
              <div className="small muted">{p.detail}</div></div>
            {job ? <JobLine job={job} />
              : p.installed ? <span className={`badge ${p.in_use ? "good" : ""}`}>{p.in_use ? "in use" : "downloaded"}</span>
              : <button className="btn sm" onClick={() => pull(p)} disabled={act.busy || !data.engine_running}>Download</button>}
          </div>
        );
      })}
      <ErrorBox error={act.error} />
    </div>
  );
}

export default function Settings() {
  const { data: sys, error, loading, reload } = useApi<any>("/api/system");
  const [s, setS] = useState<any>(null);
  const [pullModel, setPullModel] = useState("qwen2.5:7b");
  const [pullJob, setPullJob] = useState<string | null>(null);
  const [theme, setTheme] = useState(getTheme());
  const act = useAsync();
  const toast = useToast();
  const { jobs, kick } = useJobs();
  useEffect(() => { if (sys) setS(sys.settings); }, [sys]);
  if (loading || !s) return <div className="page">{error ? <ErrorBox error={error} onRetry={reload} /> : <Loading />}</div>;
  const ollama = sys.providers.find((p: any) => p.name === "ollama");
  const saveVals = async (values: any) => { if (await act.run(() => put("/api/settings", { values }))) { toast("Settings saved"); reload(); } };
  const set = (k: string, v: any) => { setS({ ...s, [k]: v }); saveVals({ [k]: v }); };
  const pull = async () => { const r = await act.run(() => post("/api/models/pull", { model: pullModel })); if (r) { setPullJob(r.job_id); kick(); } };
  const pj = jobs.find((j) => j.id === pullJob);
  const rubric = s.rubric || {};
  const totalW = Object.values(rubric).reduce((a: number, r: any) => a + Number(r.weight || 0), 0);
  const removeDemo = async () => { if (window.confirm("Remove the demo project and all its synthetic data?") && (await act.run(() => del("/api/demo")))) toast("Demo removed"); };

  return (
    <div className="page">
      <div className="page-head"><div><h1>Settings</h1><div className="sub">AI providers, privacy, keys and scoring. Everything is stored on this Mac; keys go to the macOS Keychain.</div></div></div>
      <ErrorBox error={act.error} />
      <div className="grid g2">
        <div className="stack">
          <div className="card">
            <h2>AI provider</h2>
            {sys.providers.map((p: any) => (
              <label key={p.name} className="check">
                <input type="radio" name="prov" checked={s.ai_provider === p.name} onChange={() => set("ai_provider", p.name)} />
                <span><b>{p.label}</b> {p.external ? <span className="badge warn">external · internet</span> : <span className="badge good">on this Mac</span>}{" "}
                  {p.available ? <span className="badge good">ready</span> : <span className="badge">not ready</span>}
                  <div className="small muted">{p.detail}</div></span>
              </label>
            ))}
          </div>
          <div className="card">
            <h2>Local model (Ollama)</h2>
            <label className="field"><span>Model used for analysis</span>
              <select value={s.ollama_model} onChange={(e) => set("ollama_model", e.target.value)}>
                {(ollama?.installed_models || []).concat(ollama?.installed_models?.includes(s.ollama_model) ? [] : [s.ollama_model]).map((m: string) => <option key={m}>{m}</option>)}
              </select></label>
            <label className="field"><span>Vision model for video frames & images (optional)</span>
              <select value={s.ollama_vision_model || ""} onChange={(e) => set("ollama_vision_model", e.target.value)}>
                <option value="">None — frames are stored but not described</option>
                {(ollama?.installed_models || []).filter((m: string) => VISION_RX.test(m) || m === s.ollama_vision_model).map((m: string) => <option key={m}>{m}</option>)}
                {!(ollama?.installed_models || []).some((m: string) => VISION_RX.test(m)) && <option disabled value="__none">No vision-capable model installed — download one below</option>}
              </select></label>
            <div className="row">
              <input value={pullModel} onChange={(e) => setPullModel(e.target.value)} style={{ maxWidth: 220 }} aria-label="Model to download" />
              {pj ? <JobLine job={pj} /> : <button className="btn sm" onClick={pull} disabled={act.busy}>Download model</button>}
            </div>
            <p className="help">Downloads from the Ollama library (internet). Suggestions: qwen2.5:7b (default, ~4.7 GB), qwen2.5:3b (faster). Vision and embedding models are one click below.</p>
            <Toggle on={s.use_embeddings !== false} onChange={(v) => set("use_embeddings", v)} label="Group large comment sets by meaning"
              help="Uses the local embedding model (if downloaded) when there are more comments than one analysis can read, so the sample covers every topic." />
          </div>
          <ModelPresets onDone={reload} />
          <div className="card">
            <h2>Privacy & internet</h2>
            <Toggle on={!!s.allow_external_ai} onChange={(v) => set("allow_external_ai", v)} label="Allow external AI providers"
              help="When on, Claude/OpenAI can be selected. Audience material is sent to that provider only after you confirm each analysis." />
            {s.allow_external_ai && <div className="notice warn small">External providers receive the content and comments you analyze. Don't enable for material you aren't allowed to share.</div>}
            <Toggle on={!!s.allow_web_retrieval} onChange={(v) => set("allow_web_retrieval", v)} label="Allow retrieving links I enter" help="Turn off to work fully offline; link imports will be refused." />
            <Toggle on={!!s.allow_web_research} onChange={(v) => set("allow_web_research", v)} label="Allow automated competitor research" help="Searches the web (needs a Brave Search key) and retrieves competitor pages." />
          </div>
          <div className="card">
            <h2>Transcription & text recognition</h2>
            <label className="field"><span>Whisper model (runs locally)</span>
              <select value={s.whisper_model} onChange={(e) => set("whisper_model", e.target.value)}>
                {["tiny", "base", "small", "medium"].map((m) => <option key={m}>{m}</option>)}
              </select></label>
            <p className="small muted">FFmpeg: {sys.media.ffmpeg ? "ready" : "missing"} · Whisper “{sys.media.whisper_model}”: {sys.media.whisper_model_downloaded ? "downloaded" : "downloads on first use (internet)"}. Larger models are more accurate and slower.</p>
            <p className="small muted">Text recognition (OCR) for scanned PDFs and images: {sys.media.ocr ? "ready — runs on this Mac with Apple Vision" : "unavailable — needs Apple's command-line tools (xcode-select --install)"}.</p>
          </div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>API keys</h2>
            {KEYS.map(([n, l, h]) => <SecretRow key={n} name={n} label={l} help={h} saved={!!s.secrets?.[n]} onSaved={reload} />)}
          </div>
          <div className="card">
            <h2>Opportunity scoring weights</h2>
            <p className="small muted">Higher weight = matters more. The index is relative attractiveness for testing, not a probability. Saving recalculates every opportunity.</p>
            <table className="t small">
              <thead><tr><th>Criterion</th><th>Source</th><th className="num">Weight</th><th className="num">Share</th></tr></thead>
              <tbody>{Object.entries(rubric).map(([k, r]: any) => (
                <tr key={k}><td>{r.label}</td><td><span className={`badge ${r.source === "data" ? "info" : ""}`}>{r.source}</span></td>
                  <td className="num"><input type="number" min={0} max={50} value={r.weight} style={{ width: 70 }} aria-label={r.label}
                    onChange={(e) => setS({ ...s, rubric: { ...rubric, [k]: { ...r, weight: Number(e.target.value) } } })} /></td>
                  <td className="num muted">{totalW ? Math.round((100 * r.weight) / totalW) : 0}%</td></tr>
              ))}</tbody>
            </table>
            <button className="btn sm mt" onClick={() => saveVals({ rubric })}>Save weights</button>
          </div>
          <div className="card">
            <h2>Appearance</h2>
            <div className="seg">{["system", "light", "dark"].map((t) => <button key={t} className={theme === t ? "on" : ""} onClick={() => { setTheme(t); applyTheme(t); }}>{t === "system" ? "Automatic" : t[0].toUpperCase() + t.slice(1)}</button>)}</div>
          </div>
          <div className="card">
            <h2>Data</h2>
            <p className="small">All data lives in <span className="mono">{sys.data_dir}</span>. Use Research Library → Back up database for a snapshot.</p>
            <button className="btn sm danger" onClick={removeDemo}>Remove demo project</button>
            <p className="tiny faint mt">AudienceOS {sys.version}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
