import { FormEvent, useEffect, useRef, useState } from "react";
import { evaluationsApi, getSubmissionStatus, submitAgent } from "../lib/api";
import { useNavigate } from "react-router-dom";

const tools = ["search_knowledge_base", "http_request", "database_query", "file_read", "file_write", "python_execution"];
const TERMINAL_BUILD_STATES = new Set(["build_failed"]);

export default function SubmissionPage() {
  const navigate = useNavigate();
  const timer = useRef<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [state, setState] = useState("READY FOR INTAKE");
  const [busy, setBusy] = useState(false);

  useEffect(() => () => { if (timer.current !== null) window.clearTimeout(timer.current); }, []);

  async function waitForImage(submissionId: string): Promise<void> {
    const started = Date.now();
    while (Date.now() - started < 15 * 60 * 1000) {
      const current = await getSubmissionStatus(submissionId);
      setState(`${current.build_status.toUpperCase()} · ${current.status_message ?? "waiting for builder"}`);
      if (current.build_status === "image_ready") return;
      if (TERMINAL_BUILD_STATES.has(current.build_status)) throw new Error(current.status_message ?? "Image build failed");
      await new Promise<void>((resolve) => { timer.current = window.setTimeout(resolve, 1500); });
    }
    throw new Error("Image build timed out. Check the builder worker and build log.");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) { setState("Select a source package first."); return; }
    const data = new FormData(event.currentTarget);
    const runtimeKey = String(data.get("key"));
    setBusy(true);
    setState("UPLOADING + VALIDATING");
    try {
      const result = await submitAgent(file, {
        agent_name: String(data.get("name")),
        description: String(data.get("description")),
        llm_provider: String(data.get("provider")),
        llm_model: String(data.get("model")),
        llm_api_base: String(data.get("base")),
        llm_api_key: runtimeKey,
        enabled_tools: selected,
      });
      setState("BUILD QUEUED · Dockerfile-first isolated build");
      await waitForImage(result.id);
      setState("IMAGE READY · QUEUING EVALUATION");
      const evaluation = await evaluationsApi.start(result.id, runtimeKey);
      navigate(`/report/${evaluation.evaluation_id}`);
    } catch (error) {
      setState(error instanceof Error ? error.message : "Submission failed");
      setBusy(false);
    }
  }

  return <section className="page reveal">
    <div className="page-heading compact"><div><span className="section-number">02—NEW RUN</span><h1>Submit an<br /><em>agent project.</em></h1></div><p>Dockerfile-first isolated image build.<br />Legacy agent.py packages remain compatible.</p></div>
    <form className="submission-form" onSubmit={submit}>
      <fieldset><legend>01 / IDENTITY</legend><label>AGENT NAME<input name="name" required placeholder="e.g. Research Operator" /></label><label className="wide">TASK DESCRIPTION<textarea name="description" minLength={30} required rows={4} placeholder="Describe what the agent does and what success means…" /></label></fieldset>
      <fieldset><legend>02 / MODEL ENDPOINT</legend><label>PROVIDER<select name="provider"><option>openai</option><option>anthropic</option><option>custom</option></select></label><label>MODEL<input name="model" required placeholder="model identifier" /></label><label>API BASE<input name="base" required placeholder="https://…/v1" /></label><label>API KEY<input name="key" type="password" required autoComplete="off" /></label></fieldset>
      <fieldset><legend>03 / CAPABILITIES</legend><div className="tool-grid wide">{tools.map(tool => <button type="button" onClick={() => setSelected(items => items.includes(tool) ? items.filter(x => x !== tool) : [...items, tool])} className={selected.includes(tool) ? "selected" : ""} key={tool}><i />{tool.replace(/_/g, " ")}</button>)}</div></fieldset>
      <fieldset><legend>04 / PROJECT</legend><label className="dropzone wide"><input type="file" accept=".zip,.tgz,.gz" onChange={e => setFile(e.target.files?.[0] ?? null)} /><b>{file ? file.name : "DROP OR SELECT PROJECT PACKAGE"}</b><span>ZIP · TAR.GZ · TGZ / include Dockerfile + agent-eval.yaml / max 50 MB</span></label><p className="wide">The Dockerfile owns dependencies and startup. <code>agent-eval.yaml</code> declares stdio or HTTP invocation. Without a Dockerfile, the legacy <code>agent.py</code> adapter is generated automatically.</p></fieldset>
      <div className="form-footer"><span className="form-state">{state}</span><button className="action" type="submit" disabled={busy}>BUILD + EVALUATE <b>→</b></button></div>
    </form>
  </section>;
}
