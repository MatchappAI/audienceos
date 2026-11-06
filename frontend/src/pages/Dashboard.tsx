import { Link, useNavigate } from "react-router-dom";
import { post } from "../api";
import { ago, money, num } from "../format";
import { Empty, ErrorBox, JobLine, Loading, Stat, useApi, useAsync, useJobs } from "../components/ui";

const ACTION_ICON: Record<string, string> = { setup: "⚙", import: "＋", analyze: "◇", experiment: "△", decide: "✓" };

export default function Dashboard() {
  const { data, error, loading, reload } = useApi<any>("/api/dashboard");
  const { kick } = useJobs();
  const nav = useNavigate();
  const demo = useAsync();

  const loadDemo = async () => {
    const r = await demo.run(() => post("/api/demo"));
    if (r) {
      kick();
      nav(`/audiences/${r.audience_id}/sources`);
    }
  };

  if (loading) return <div className="page"><Loading /></div>;
  if (error || !data) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  const s = data.stats;
  const isEmpty = !s.audiences;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <div className="sub">Every number here is calculated from data stored on this Mac.</div>
        </div>
        <div className="row">
          {!s.has_demo && (
            <button className="btn" onClick={loadDemo} disabled={demo.busy}>
              {demo.busy ? "Loading demo…" : "Load demo project"}
            </button>
          )}
          <Link className="btn primary" to="/audiences?new=1">Add creator</Link>
        </div>
      </div>
      <ErrorBox error={demo.error} />

      {isEmpty ? (
        <div className="card">
          <Empty
            title="No audiences yet"
            actions={
              <>
                <Link className="btn primary" to="/audiences?new=1">Add your first creator</Link>
                <button className="btn" onClick={loadDemo} disabled={demo.busy}>Load demo project</button>
              </>
            }
          >
            Add a creator or business, import their content and comments, and AudienceOS will find what their audience
            struggles with and what they might pay for. The demo project uses clearly labeled synthetic data.
          </Empty>
        </div>
      ) : (
        <>
          <div className="grid g4">
            <Stat label="Audiences researched" value={num(s.audiences_analyzed)} hint={`${num(s.audiences)} total · ${num(s.active_projects)} active this month`} />
            <Stat label="Product opportunities" value={num(s.opportunities)} hint={`${num(s.awaiting_validation)} awaiting validation`} />
            <Stat label="Validated opportunities" value={num(s.validated)} hint={`${num(s.active_experiments)} experiments running`} />
            <Stat label="Recorded sales" value={num(s.sales)} hint={<>{money(s.revenue)} net from experiments{s.demo_sales ? ` · ${num(s.demo_sales)} demo sales excluded` : ""}</>} />
          </div>

          <div className="grid g3 mt">
            <Stat label="Product sales" value={money(s.product_net_sales)} hint={`${num(s.product_orders)} orders on launched products (excl. demo)`} />
            <Stat label="Owed to creators" value={money(s.creator_balance_owed)} hint={<>{s.has_demo ? "excl. demo · " : ""}<Link to="/creators">Creators & Revenue →</Link></>} />
            <Stat label="Launched products" value={num(s.launched_products)} hint={`approved and live on your storefronts${s.has_demo ? " (excl. demo)" : ""}`} />
          </div>

          <div className="grid g2 mt2">
            <div className="card">
              <h2>Next recommended actions</h2>
              {data.next_actions.length === 0 ? (
                <p className="muted">Nothing pending. Add more sources or start a validation experiment.</p>
              ) : (
                <ul className="clean">
                  {data.next_actions.map((a: any, i: number) => (
                    <li key={i} className="row top" style={{ flexWrap: "nowrap" }}>
                      <span className="nav-ico" aria-hidden style={{ flex: "none" }}>{ACTION_ICON[a.kind] || "•"}</span>
                      <Link to={a.link}>{a.text}</Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="card">
              <h2>Recent activity</h2>
              {data.activity.length === 0 ? (
                <p className="muted">No activity yet.</p>
              ) : (
                <ul className="clean small">
                  {data.activity.map((a: any) => (
                    <li key={a.id} className="row between top">
                      <span>
                        {a.audience_id ? <Link to={`/audiences/${a.audience_id}`}>{a.audience_name}</Link> : null}
                        {a.audience_id ? " — " : ""}
                        {a.message}
                      </span>
                      <span className="faint" style={{ whiteSpace: "nowrap" }}>{ago(a.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {data.active_jobs.length > 0 && (
            <div className="card mt2">
              <h2>Working on it</h2>
              <ul className="clean">
                {data.active_jobs.map((j: any) => (
                  <li key={j.id} className="row between">
                    <span>
                      {j.audience_name && <Link to={`/audiences/${j.audience_id}`}>{j.audience_name}</Link>}{" "}
                      <span className="muted small">{j.kind.replace(/_/g, " ")}</span>
                    </span>
                    <JobLine job={j} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
