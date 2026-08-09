import { FormEvent, useState } from "react";
import { submitAgent } from "../lib/api";
import { evaluationsApi } from "../lib/api";
import { useNavigate } from "react-router-dom";

const tools = ["search_knowledge_base", "http_request", "database_query", "file_read", "file_write", "python_execution"];
export default function SubmissionPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null); const [selected, setSelected] = useState<string[]>([]); const [state, setState] = useState<string>("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!file) return setState("Select a source package first.");
    const data = new FormData(event.currentTarget); setState("UPLOADING + VALIDATING…");
    try { const result = await submitAgent(file, { agent_name: String(data.get("name")), description: String(data.get("description")), llm_provider: String(data.get("provider")), llm_model: String(data.get("model")), llm_api_base: String(data.get("base")), llm_api_key: String(data.get("key")), enabled_tools: selected }); setState(`ACCEPTED · QUEUING EVALUATION…`); const evaluation = await evaluationsApi.start(result.id); navigate(`/report/${evaluation.evaluation_id}`); }
    catch (error) { setState(error instanceof Error ? error.message : "Submission failed"); }
  }
  return <section className="page reveal"><div className="page-heading compact"><div><span className="section-number">02—NEW RUN</span><h1>Submit an<br /><em>agent package.</em></h1></div><p>Source is scanned before any execution.<br />Credentials remain runtime-only.</p></div>
    <form className="submission-form" onSubmit={submit}><fieldset><legend>01 / IDENTITY</legend><label>AGENT NAME<input name="name" required placeholder="e.g. Research Operator" /></label><label className="wide">TASK DESCRIPTION<textarea name="description" minLength={30} required rows={4} placeholder="Describe what the agent does and what success means…" /></label></fieldset>
    <fieldset><legend>02 / MODEL ENDPOINT</legend><label>PROVIDER<select name="provider"><option>openai</option><option>anthropic</option><option>custom</option></select></label><label>MODEL<input name="model" required placeholder="model identifier" /></label><label>API BASE<input name="base" required placeholder="https://…/v1" /></label><label>API KEY<input name="key" type="password" required autoComplete="off" /></label></fieldset>
    <fieldset><legend>03 / CAPABILITIES</legend><div className="tool-grid wide">{tools.map(tool => <button type="button" onClick={() => setSelected(items => items.includes(tool) ? items.filter(x => x !== tool) : [...items, tool])} className={selected.includes(tool) ? "selected" : ""} key={tool}><i />{tool.replace(/_/g, " ")}</button>)}</div></fieldset>
    <fieldset><legend>04 / SOURCE</legend><label className="dropzone wide"><input type="file" accept=".zip,.tgz,.gz" onChange={e => setFile(e.target.files?.[0] ?? null)} /><b>{file ? file.name : "DROP OR SELECT PACKAGE"}</b><span>ZIP · TAR.GZ · TGZ / MAX 50 MB</span></label></fieldset>
    <div className="form-footer"><span className="form-state">{state || "READY FOR INTAKE"}</span><button className="action" type="submit">VALIDATE + QUEUE <b>↗</b></button></div></form>
  </section>;
}
