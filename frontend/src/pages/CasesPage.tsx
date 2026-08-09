import { useEffect, useState } from "react";
import { casesApi, TestCase } from "../lib/api";

export default function CasesPage() {
  const [filter, setFilter] = useState("ALL"); const [items, setItems] = useState<TestCase[]>([]); const [error, setError] = useState("");
  useEffect(() => { casesApi.list().then(data => setItems(data.items)).catch(error => setError(error.message)); }, []);
  const cases = filter === "ALL" ? items : items.filter(item => item.tier.toUpperCase() === filter);
  return <section className="page reveal"><div className="page-heading compact"><div><span className="section-number">05—CASE BANK</span><h1>Evaluation <em>inventory.</em></h1></div></div><div className="case-toolbar"><div>{["ALL", "CORE", "REGRESSION", "ADVERSARIAL"].map(item => <button className={filter === item ? "active" : ""} onClick={() => setFilter(item)} key={item}>{item}</button>)}</div><span>{cases.length} CASES SHOWN</span></div><article className="panel case-table"><div className="run-row header"><span>CASE / PROMPT</span><span>TIER</span><span>AGENT TYPE</span><span>STATE</span><span /></div>{cases.map(item => <div className="run-row" key={item.id}><span><small>{item.task_id}</small><b>{item.prompt}</b></span><span>{item.tier}</span><span>{item.agent_type}</span><span className={`badge ${item.status === "draft" ? "review" : "passed"}`}>{item.status}</span><button>OPEN ↗</button></div>)}</article>{!cases.length && <p className="empty-state">{error || "No cases match this tier."}</p>}</section>;
}
