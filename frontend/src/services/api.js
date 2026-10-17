// All backend calls live here. Components never call fetch directly.
const BASE = import.meta.env.VITE_API_URL || "";
const KEY = import.meta.env.VITE_API_KEY || "";

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(KEY ? { Authorization: `Bearer ${KEY}` } : {}) };
  let response;
  try {
    response = await fetch(`${BASE}/api${path}`, { ...options, headers });
  } catch {
    throw new Error("Cannot reach the DevPilot API. Is the backend running on port 8000?");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}

export const api = {
  health: () => request("/health"),
  inspect: (repository_url) => request("/repositories/inspect", { method: "POST", body: JSON.stringify({ repository_url }) }),
  startAnalysis: (repository_url, task) =>
    request("/analysis", { method: "POST", body: JSON.stringify({ repository_url, task }) }),
  listTasks: () => request("/tasks"),
  getTask: (id) => request(`/tasks/${id}`),
  getFindings: (id) => request(`/tasks/${id}/findings`),
  getPatch: (id) => request(`/tasks/${id}/patch`),
  decide: (id, approved, note) => request(`/tasks/${id}/approve`, { method: "POST", body: JSON.stringify({ approved, note }) }),
  getReport: (id) => request(`/tasks/${id}/report`),
};
