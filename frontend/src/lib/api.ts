const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/v1";
const TOKEN_KEY = "agent_eval_access_token";

export const auth = {
  token: () => sessionStorage.getItem(TOKEN_KEY),
  setToken: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = auth.token();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) auth.clear();
    throw new Error(payload?.error?.message ?? payload?.detail ?? `Request failed (${response.status})`);
  }
  return payload as T;
}

export async function login(username: string, password: string) {
  const result = await api<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  auth.setToken(result.access_token);
  return result;
}

export async function register(username: string, email: string, password: string) {
  return api<{ id: string }>("/auth/register", { method: "POST", body: JSON.stringify({ username, email, password }) });
}

export type SubmissionForm = {
    agent_name: string; description: string; llm_provider: string; llm_model: string;
    llm_api_base: string; agent_type: "short_horizon" | "long_horizon"; subtype?: string; enabled_tools: string[];
};

export async function submitAgent(
  source: File, compose: File, runtimeConfig: File, interfaceSpec: File, metadata: SubmissionForm,
) {
  const form = new FormData();
  form.append("source", source);
  form.append("compose", compose);
  form.append("runtime_config", runtimeConfig);
  form.append("interface_spec", interfaceSpec);
  form.append("metadata_json", JSON.stringify(metadata));
  return api<{ id: string; status: string; risk_level: string }>("/submissions/verified", { method: "POST", body: form });
}

export type SubmissionStatus = {
  id: string;
  status: string;
  build_mode: "compose";
  build_status: string;
  runtime_protocol: "stdio" | "http";
  image_ref: string | null;
  image_digest: string | null;
  status_message: string | null;
};

export function getSubmissionStatus(id: string) {
  return api<SubmissionStatus>(`/submissions/${id}/status`);
}

export type EvaluationSummary = { id: string; agent_name: string; agent_type: string; overall_score: number | null; grade: string | null; status: string; created_at: string };
export type EvaluationReport = { id: string; status: string; agent_type: string; horizon: string; overall_score: number | null; grade: string | null; dimensions: Record<string, number> | null; improvement_suggestions: Array<{ severity: string; category: string; description: string; recommendation: string }>; created_at?: string };
export type Trace = { spans: Array<Record<string, unknown>> };
export type EvaluationCaseSummary = {
  id: string; case_key: string; title: string; suite: string; status: string;
  capability_ids: string[]; dimension_scores: Record<string, number> | null;
  unknown_weight: number | null; error_code: string | null;
};
export type TestCase = { id: string; task_id: string; agent_type: string; tier: string; status: string; prompt: string };

export const evaluationsApi = {
  list: () => api<{ items: EvaluationSummary[] }>("/evaluations"),
  report: (id: string) => api<EvaluationReport>(`/evaluations/${id}/report`),
  trace: (id: string) => api<Trace>(`/evaluations/${id}/trace`),
  cases: (id: string) => api<{ items: EvaluationCaseSummary[] }>(`/evaluations/${id}/cases`),
  start: (submissionId: string, llmApiKey: string, caseSetId?: string) => api<{ evaluation_id: string }>(`/evaluations/${submissionId}/start`, { method: "POST", body: JSON.stringify({ llm_api_key: llmApiKey, case_set_id: caseSetId ?? null }) }),
};

export type CaseSetSummary = { id: string; version: number; status: string; target_case_count: number; actual_case_count: number };
export const caseSetsApi = {
  generate: (submissionId: string, targetCount?: number) => api<{ task_id: string }>(`/submissions/${submissionId}/case-sets/generate`, {
    method: "POST", body: JSON.stringify({ target_count: targetCount ?? null }),
  }),
  list: (submissionId: string) => api<{ items: CaseSetSummary[] }>(`/submissions/${submissionId}/case-sets`),
};

export const casesApi = {
  list: () => api<{ items: TestCase[]; total: number }>("/test-cases"),
};
