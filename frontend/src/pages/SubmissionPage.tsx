import { FormEvent, useEffect, useRef, useState } from "react";
import { caseSetsApi, evaluationsApi, getSubmissionStatus, submitAgent } from "../lib/api";
import { useNavigate } from "react-router-dom";

const tools = ["search_knowledge_base", "http_request", "database_query", "file_read", "file_write", "python_execution"];
const TERMINAL_BUILD_STATES = new Set(["build_failed", "image_rejected", "validation_failed"]);
const TERMINAL_CASE_STATES = new Set(["ready", "needs_review", "validation_failed"]);

export default function SubmissionPage() {
  const navigate = useNavigate();
  const timer = useRef<number | null>(null);
  const [source, setSource] = useState<File | null>(null);
  const [compose, setCompose] = useState<File | null>(null);
  const [runtimeConfig, setRuntimeConfig] = useState<File | null>(null);
  const [interfaceSpec, setInterfaceSpec] = useState<File | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [state, setState] = useState("READY FOR VERIFIED INTAKE");
  const [busy, setBusy] = useState(false);

  useEffect(() => () => { if (timer.current !== null) window.clearTimeout(timer.current); }, []);

  async function pause() {
    await new Promise<void>((resolve) => { timer.current = window.setTimeout(resolve, 1500); });
  }

  async function waitForImage(submissionId: string): Promise<void> {
    const started = Date.now();
    while (Date.now() - started < 15 * 60 * 1000) {
      const current = await getSubmissionStatus(submissionId);
      setState(`${current.build_status.toUpperCase()} · ${current.status_message ?? "waiting for isolated builder"}`);
      if (current.build_status === "image_ready") return;
      if (TERMINAL_BUILD_STATES.has(current.build_status)) throw new Error(current.status_message ?? "Image build failed");
      await pause();
    }
    throw new Error("Image build timed out. Check the builder worker and build log.");
  }

  async function waitForCaseSet(submissionId: string): Promise<string> {
    const started = Date.now();
    while (Date.now() - started < 20 * 60 * 1000) {
      const { items } = await caseSetsApi.list(submissionId);
      const latest = items[0];
      if (latest) {
        setState(`CASE COUNCIL ${latest.status.toUpperCase()} · ${latest.actual_case_count}/${latest.target_case_count}`);
        if (latest.status === "ready") return latest.id;
        if (TERMINAL_CASE_STATES.has(latest.status)) {
          throw new Error(`Case Set did not pass the quality gate: ${latest.status}`);
        }
      }
      await pause();
    }
    throw new Error("Case Council timed out.");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!source || !compose || !runtimeConfig || !interfaceSpec) {
      setState("Select source, Compose, runtime config and interface specification.");
      return;
    }
    const data = new FormData(event.currentTarget);
    const runtimeKey = String(data.get("key"));
    setBusy(true);
    setState("UPLOADING + VERIFYING FOUR ARTIFACTS");
    try {
      const result = await submitAgent(source, compose, runtimeConfig, interfaceSpec, {
        agent_name: String(data.get("name")),
        description: String(data.get("description")),
        llm_provider: String(data.get("provider")),
        llm_model: String(data.get("model")),
        llm_api_base: String(data.get("base")),
        agent_type: String(data.get("agent_type")) as "short_horizon" | "long_horizon",
        enabled_tools: selected,
      });
      setState("BUILD QUEUED · VERIFIED MANIFEST CREATED");
      await waitForImage(result.id);
      setState("IMAGE READY · STARTING CASE COUNCIL");
      await caseSetsApi.generate(result.id);
      const caseSetId = await waitForCaseSet(result.id);
      setState("CASE SET READY · QUEUING MULTI-CASE EVALUATION");
      const evaluation = await evaluationsApi.start(result.id, runtimeKey, caseSetId);
      navigate(`/report/${evaluation.evaluation_id}`);
    } catch (error) {
      setState(error instanceof Error ? error.message : "Submission failed");
      setBusy(false);
    }
  }

  return <section className="page reveal">
    <div className="page-heading compact"><div><span className="section-number">02—NEW RUN</span><h1>Submit an<br /><em>agent project.</em></h1></div><p>One verified protocol for single-service and multi-service Agents.<br />Compose declares topology; the platform rebuilds it safely.</p></div>
    <form className="submission-form" onSubmit={submit}>
      <fieldset><legend>01 / IDENTITY</legend><label>AGENT NAME<input name="name" required placeholder="e.g. Research Operator" /></label><label>AGENT TYPE<select name="agent_type"><option value="short_horizon">Short horizon</option><option value="long_horizon">Long horizon</option></select></label><label className="wide">FUNCTION AND PURPOSE<textarea name="description" minLength={30} required rows={4} placeholder="Describe the Agent's complete function, purpose and success criteria." /></label></fieldset>
      <fieldset><legend>02 / MODEL RUNTIME</legend><label>PROVIDER<select name="provider"><option>openai</option><option>anthropic</option><option>custom</option></select></label><label>MODEL<input name="model" required placeholder="model identifier" /></label><label>API BASE<input name="base" required placeholder="https://api.example.com/v1" /></label><label>EPHEMERAL API KEY<input name="key" type="password" required autoComplete="off" /></label><p className="wide">The API key is stored in the expiring credential vault and injected only into evaluation containers. It is never written to the source Artifact, Manifest or image.</p></fieldset>
      <fieldset><legend>03 / DECLARED TOOLS</legend><div className="tool-grid wide">{tools.map(tool => <button type="button" onClick={() => setSelected(items => items.includes(tool) ? items.filter(x => x !== tool) : [...items, tool])} className={selected.includes(tool) ? "selected" : ""} key={tool}><i />{tool.replace(/_/g, " ")}</button>)}</div></fieldset>
      <fieldset><legend>04 / VERIFIED ARTIFACTS</legend>
        <label className="dropzone"><input type="file" accept=".zip,.tgz,.gz" onChange={event => setSource(event.target.files?.[0] ?? null)} /><b>{source?.name ?? "SOURCE PACKAGE"}</b><span>ZIP · TAR.GZ · TGZ / max 50 MB</span></label>
        <label className="dropzone"><input type="file" accept=".yaml,.yml" onChange={event => setCompose(event.target.files?.[0] ?? null)} /><b>{compose?.name ?? "DOCKER COMPOSE"}</b><span>Safe topology declaration only</span></label>
        <label className="dropzone"><input type="file" accept=".yaml,.yml,.json" onChange={event => setRuntimeConfig(event.target.files?.[0] ?? null)} /><b>{runtimeConfig?.name ?? "RUNTIME CONFIG"}</b><span>Entry service · protocol · secrets · network</span></label>
        <label className="dropzone"><input type="file" accept=".yaml,.yml,.json" onChange={event => setInterfaceSpec(event.target.files?.[0] ?? null)} /><b>{interfaceSpec?.name ?? "CLI / OPENAPI SPEC"}</b><span>Every declared command or operation is tested</span></label>
        <p className="wide">No user Manifest is required. The platform validates these four immutable Artifacts, generates a Verified Manifest, builds and scans every service image, then creates a capability-complete Case Set.</p>
      </fieldset>
      <div className="form-footer"><span className="form-state">{state}</span><button className="action" type="submit" disabled={busy}>BUILD + COUNCIL + EVALUATE <b>→</b></button></div>
    </form>
  </section>;
}
