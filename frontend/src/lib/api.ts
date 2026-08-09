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
  llm_api_base: string; llm_api_key: string; subtype?: string; enabled_tools: string[];
};

export async function submitAgent(file: File, config: SubmissionForm) {
  const form = new FormData();
  form.append("package", file);
  form.append("config_data", JSON.stringify(config));
  return api<{ id: string; status: string; risk_level: string }>("/submissions", { method: "POST", body: form });
}

export type EvaluationSummary = { id: string; agent_name: string; agent_type: string; overall_score: number | null; grade: string | null; status: string; created_at: string };
export type EvaluationReport = { id: string; status: string; agent_type: string; horizon: string; overall_score: number | null; grade: string | null; dimensions: Record<string, number> | null; improvement_suggestions: Array<{ severity: string; category: string; description: string; recommendation: string }>; created_at?: string };
export type Trace = { spans: Array<Record<string, unknown>> };
export type TestCase = { id: string; task_id: string; agent_type: string; tier: string; status: string; prompt: string };

export const evaluationsApi = {
  list: () => api<{ items: EvaluationSummary[] }>("/evaluations"),
  report: (id: string) => api<EvaluationReport>(`/evaluations/${id}/report`),
  trace: (id: string) => api<Trace>(`/evaluations/${id}/trace`),
  start: (submissionId: string) => api<{ evaluation_id: string }>(`/evaluations/${submissionId}/start`, { method: "POST" }),
};

export const casesApi = {
  list: () => api<{ items: TestCase[]; total: number }>("/test-cases"),
};
