import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { EvidenceProvider } from "./components/evidence";
import { JobsProvider, ToastProvider, useJobs } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import Research from "./pages/Research";
import Workspace from "./pages/Workspace";
import IntelligencePage from "./pages/Intelligence";
import Opportunities from "./pages/Opportunities";
import OpportunityDetail from "./pages/OpportunityDetail";
import Validation from "./pages/Validation";
import ExperimentDetail from "./pages/ExperimentDetail";
import Library from "./pages/Library";
import Creators, { CreatorDetail } from "./pages/Creators";
import ProductDetail from "./pages/ProductDetail";
import Settings from "./pages/Settings";

export function getTheme(): string {
  try {
    return localStorage.getItem("aos-theme") || "system";
  } catch {
    return "system";
  }
}
export function applyTheme(t: string) {
  const root = document.documentElement;
  if (t === "light" || t === "dark") root.setAttribute("data-theme", t);
  else root.removeAttribute("data-theme");
  try {
    localStorage.setItem("aos-theme", t);
  } catch {
    /* storage unavailable */
  }
}

const NAV = [
  { to: "/", label: "Dashboard", ico: "◎", end: true },
  { to: "/audiences", label: "Audience Research", ico: "＋" },
  { to: "/intelligence", label: "Audience Intelligence", ico: "◇" },
  { to: "/opportunities", label: "Product Opportunities", ico: "◆" },
  { to: "/validation", label: "Validation Lab", ico: "△" },
  { to: "/library", label: "Research Library", ico: "▤" },
];

function ActiveJobsBadge() {
  const { jobs } = useJobs();
  if (!jobs.length) return null;
  return (
    <div className="small muted row" style={{ padding: "8px 10px" }}>
      <span className="spinner" /> {jobs.length} task{jobs.length > 1 ? "s" : ""} running
    </div>
  );
}

function ThemeToggle() {
  const [t, setT] = useState(getTheme());
  useEffect(() => applyTheme(t), [t]);
  const next = t === "system" ? "light" : t === "light" ? "dark" : "system";
  return (
    <button className="btn ghost sm" onClick={() => setT(next)} title="Switch appearance">
      {t === "system" ? "◐ Auto" : t === "light" ? "☀ Light" : "☾ Dark"}
    </button>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <JobsProvider>
        <EvidenceProvider>
          <div className="app">
            <nav className="side" aria-label="Main">
              <div className="brand">
                <svg className="brand-mark" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><defs><linearGradient id="aosMarkG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3a95ff"/><stop offset=".55" stopColor="#0a66c2"/><stop offset="1" stopColor="#0a3f86"/></linearGradient></defs><rect width="32" height="32" rx="8" fill="url(#aosMarkG)"/><circle cx="8.6" cy="23.4" r="3.1" fill="#fff"/><circle cx="8.60" cy="15.20" r="1.55" fill="#fff" fillOpacity="1"/><circle cx="14.40" cy="17.60" r="1.55" fill="#fff" fillOpacity="1"/><circle cx="16.80" cy="23.40" r="1.55" fill="#fff" fillOpacity="1"/><circle cx="8.60" cy="8.40" r="1.55" fill="#fff" fillOpacity="0.82"/><circle cx="14.34" cy="9.54" r="1.55" fill="#fff" fillOpacity="0.82"/><circle cx="19.21" cy="12.79" r="2.5" fill="#ffc24a"/><circle cx="22.46" cy="17.66" r="1.55" fill="#fff" fillOpacity="0.82"/><circle cx="23.60" cy="23.40" r="1.55" fill="#fff" fillOpacity="0.82"/></svg> AudienceOS
              </div>
              <div className="nav">
                {NAV.map((n) => (
                  <NavLink key={n.to} to={n.to} end={n.end}>
                    <span className="nav-ico" aria-hidden>{n.ico}</span>
                    {n.label}
                  </NavLink>
                ))}
                <div className="sep" />
                <NavLink to="/creators">
                  <span className="nav-ico" aria-hidden>$</span>Creators & Revenue
                </NavLink>
              </div>
              <div className="side-foot nav">
                <ActiveJobsBadge />
                <NavLink to="/settings">
                  <span className="nav-ico" aria-hidden>⚙</span>Settings
                </NavLink>
                <div style={{ padding: "6px 4px" }}>
                  <ThemeToggle />
                </div>
              </div>
            </nav>
            <main className="main">
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/audiences" element={<Research />} />
                <Route path="/audiences/:id" element={<Workspace />} />
                <Route path="/audiences/:id/:tab" element={<Workspace />} />
                <Route path="/intelligence" element={<IntelligencePage />} />
                <Route path="/intelligence/:id" element={<IntelligencePage />} />
                <Route path="/opportunities" element={<Opportunities />} />
                <Route path="/opportunities/:id" element={<OpportunityDetail />} />
                <Route path="/validation" element={<Validation />} />
                <Route path="/validation/:id" element={<ExperimentDetail />} />
                <Route path="/library" element={<Library />} />
                <Route path="/creators" element={<Creators />} />
                <Route path="/creators/:id" element={<CreatorDetail />} />
                <Route path="/products/:id" element={<ProductDetail />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" />} />
              </Routes>
            </main>
          </div>
        </EvidenceProvider>
      </JobsProvider>
    </ToastProvider>
  );
}
