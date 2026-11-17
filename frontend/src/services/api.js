
// const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// async function apiRequest(endpoint) {
//   if (!API_BASE_URL) {
//     throw new Error("VITE_API_BASE_URL is not configured");
//   }

//   const response = await fetch(`${API_BASE_URL}${endpoint}`);

//   if (!response.ok) {
//     throw new Error(`API request failed: ${response.status}`);
//   }

//   return response.json();
// }

// export const getHealth = () => apiRequest("/health");

// export const getMetrics = () => apiRequest("/metrics");

// export const getTasks = () => apiRequest("/dashboard/tasks");

// export const getTraces = () => apiRequest("/dashboard/traces");

// export const getPendingApprovals = () =>
//   apiRequest("/tasks/pending/approvals");












const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function getApiUrl(endpoint) {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not configured");
  }

  return `${API_BASE_URL.replace(/\/$/, "")}${endpoint}`;
}

async function apiRequest(endpoint, options = {}) {
  const response = await fetch(getApiUrl(endpoint), {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `API request failed: ${response.status}`
    );
  }

  return response.json();
}

// Health and monitoring
export const getHealth = () => apiRequest("/health");
export const getMetrics = () => apiRequest("/metrics");
export const getTasks = () => apiRequest("/dashboard/tasks");
export const getTraces = () => apiRequest("/dashboard/traces");
export const getPendingApprovals = () =>
  apiRequest("/tasks/pending/approvals");

// Task details
export const getTaskDetails = (taskId) =>
  apiRequest(`/tasks/${encodeURIComponent(taskId)}`);

// Approve or reject an action
export const resolveApproval = (taskId, approved) =>
  apiRequest(`/tasks/${encodeURIComponent(taskId)}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });

// Batch task execution
export const createBatchTasks = (tasks) =>
  apiRequest("/tasks/batch", {
    method: "POST",
    body: JSON.stringify({ tasks }),
  });

// Single task execution with Server-Sent Events
export async function createTaskStream(
  task,
  onEvent,
  signal
) {
  const response = await fetch(getApiUrl("/tasks"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(task),
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `Task request failed: ${response.status}`
    );
  }

  if (!response.body) {
    throw new Error("Streaming response is not supported by this browser");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || "";

      for (const rawEvent of events) {
        const lines = rawEvent.split(/\r?\n/);

        let eventName = "message";
        let data = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            data += line.slice(5).trim();
          }
        }

        if (data) {
          let parsedData;

          try {
            parsedData = JSON.parse(data);
          } catch {
            parsedData = { message: data };
          }

          onEvent?.({
            event: eventName,
            data: parsedData,
          });
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

