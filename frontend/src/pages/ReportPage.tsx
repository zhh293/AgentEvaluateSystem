import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import RadarScore from "../components/RadarScore";
import { EvaluationReport, evaluationsApi } from "../lib/api";

const names = ["result", "trajectory", "efficiency", "security"];
export default function ReportPage() {
  const { id = "" } = useParams(); const [report, setReport] = useState<EvaluationReport | null>(null); const [error, setError] = useState("");
  useEffect(() => { let timer: number; const load = () => evaluationsApi.report(id).then(data => { setReport(data); if (["queued", "running"].includes(data.status)) timer = window.setTimeout(load, 2500); }).catch(error => setError(error.message)); load(); return () => clearTimeout(timer); }, [id]);
  if (!report) return <section className="page reveal"><p className="empty-state">{error || "Loading evaluation…"}</p></section>;
  const dimensions = names.map(name => ({ n: name.toUpperCase(), s: report.dimensions?.[name] ?? 0, w: report.horizon === "long" ? ({ result: 30, trajectory: 30, efficiency: 20, security: 20 } as Record<string, number>)[name] : ({ result: 40, trajectory: 20, efficiency: 20, security: 20 } as Record<string, number>)[name] }));
  return <section className="page reveal"><div className="report-title"><div><span className="section-number">03—REPORT / {id.slice(0, 8)}</span><h1>Evaluation <em>{report.status}.</em></h1><p>{report.agent_type} · {report.horizon} HORIZON</p></div><div className="grade"><span>GRADE</span><strong>{report.grade ?? "—"}</strong><b>{report.overall_score ?? "—"}</b></div></div>
    {report.dimensions ? <><div className="report-grid"><article className="panel radar-panel"><div className="panel-head"><h2>Dimensional profile</h2><span>WEIGHTED</span></div><RadarScore scores={dimensions.map(x => x.s)} /></article><article className="panel dimension-panel"><div className="panel-head"><h2>Score ledger</h2><span>4 DIMENSIONS</span></div>{dimensions.map(item => <div className="dimension-row" key={item.n}><span>{item.n}<small>{item.w}% WEIGHT</small></span><div><i style={{ width: `${item.s}%` }} /></div><strong>{item.s}</strong></div>)}</article></div><article className="panel findings"><div className="panel-head"><h2>Priority findings</h2><Link to={`/trace/${id}`}>VIEW TRACE ↗</Link></div>{report.improvement_suggestions?.map((item, i) => <div className="finding-row" key={`${item.category}-${i}`}><b>0{i + 1}</b><span className={`severity ${item.severity.toLowerCase()}`}>{item.severity}</span><div><small>{item.category}</small><strong>{item.description}</strong><p>{item.recommendation}</p></div></div>)}{!report.improvement_suggestions?.length && <p className="empty-state">No improvement findings were generated.</p>}</article></> : <p className="empty-state">Evaluation is {report.status}. This page refreshes while work is in flight.</p>}
  </section>;
}
