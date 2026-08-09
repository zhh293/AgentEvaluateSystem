import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import MetricCard from "../components/MetricCard";
import { EvaluationSummary, evaluationsApi } from "../lib/api";

export default function DashboardPage() {
  const [runs, setRuns] = useState<EvaluationSummary[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { evaluationsApi.list().then(data => setRuns(data.items)).catch(error => setError(error.message)); }, []);
  const stats = useMemo(() => {
    const completed = runs.filter(run => run.status === "completed" && run.overall_score != null);
    const passed = completed.filter(run => (run.overall_score ?? 0) >= 60).length;
    return { total: runs.length, completed: completed.length, passRate: completed.length ? Math.round(passed / completed.length * 100) : 0 };
  }, [runs]);
  return <section className="page reveal">
    <div className="page-heading"><div><span className="section-number">01—OVERVIEW</span><h1>Evaluation<br /><em>operations.</em></h1></div><Link className="action" to="/submit">START NEW RUN <b>↗</b></Link></div>
    <div className="metric-grid"><MetricCard label="TOTAL RUNS" value={String(stats.total)} /><MetricCard label="PASS RATE" value={`${stats.passRate}%`} tone={stats.passRate >= 85 ? "good" : "warn"} /><MetricCard label="COMPLETED" value={String(stats.completed)} /><MetricCard label="IN FLIGHT" value={String(runs.length - stats.completed)} /></div>
    <article className="panel run-panel"><div className="panel-head"><h2>Recent evaluations</h2><span>LIVE DATA</span></div><div className="run-table"><div className="run-row header"><span>RUN / AGENT</span><span>TYPE</span><span>SCORE</span><span>STATE</span><span>CREATED</span></div>{runs.map(run => <Link to={`/report/${run.id}`} className="run-row" key={run.id}><span><small>{run.id.slice(0, 8)}</small><b>{run.agent_name}</b></span><span>{run.agent_type}</span><strong>{run.overall_score ?? "—"}</strong><span className={`badge ${run.status === "completed" ? "passed" : "review"}`}>{run.status}</span><span>{new Date(run.created_at).toLocaleTimeString()}</span></Link>)}</div>{!runs.length && <p className="empty-state">{error || "No evaluations yet. Start the first run."}</p>}</article>
  </section>;
}
