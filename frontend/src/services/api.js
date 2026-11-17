
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function apiRequest(endpoint) {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not configured");
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json();
}

export const getHealth = () => apiRequest("/health");

export const getMetrics = () => apiRequest("/metrics");

export const getTasks = () => apiRequest("/dashboard/tasks");

export const getTraces = () => apiRequest("/dashboard/traces");

export const getPendingApprovals = () =>
  apiRequest("/tasks/pending/approvals");
