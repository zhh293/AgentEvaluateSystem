import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import SubmissionPage from "./pages/SubmissionPage";
import ReportPage from "./pages/ReportPage";
import TracePage from "./pages/TracePage";
import CasesPage from "./pages/CasesPage";
import LoginPage from "./pages/LoginPage";
import { auth } from "./lib/api";
import { useState } from "react";

const links = [
  ["/", "OVERVIEW", "01"],
  ["/submit", "NEW RUN", "02"],
  ["/cases", "CASE BANK", "03"],
];

function Shell({ onLogout }: { onLogout: () => void }) {
  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="brand-mark">AE<span>/</span></div>
        <nav aria-label="Main navigation">
          {links.map(([to, label, index]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `rail-link ${isActive ? "active" : ""}`}>
              <small>{index}</small><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot"><i />SYSTEM<br />READY</div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">AGENT EVALUATION SYSTEM</span><b>CONTROL ROOM</b></div>
          <div className="top-status"><span>UTC+08</span><span className="signal">LIVE</span><button className="text-button" onClick={onLogout}>LOG OUT</button></div>
        </header>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/submit" element={<SubmissionPage />} />
          <Route path="/report/:id" element={<ReportPage />} />
          <Route path="/trace/:id" element={<TracePage />} />
          <Route path="/cases" element={<CasesPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(auth.token()));
  if (!authenticated) return <LoginPage onAuthenticated={() => setAuthenticated(true)} />;
  return <BrowserRouter><Shell onLogout={() => { auth.clear(); setAuthenticated(false); }} /></BrowserRouter>;
}
