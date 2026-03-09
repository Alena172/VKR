const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const AUTH_TOKEN_KEY = "vkr_auth_token";

export function setAuthToken(token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

async function request(path, options = {}) {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function toQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    search.append(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

/**
 * Poll a Celery task until it reaches SUCCESS or FAILURE.
 *
 * @param {string} taskId - The task ID returned by a 202 endpoint.
 * @param {object} options
 * @param {number} [options.intervalMs=1000] - Polling interval in ms.
 * @param {number} [options.maxAttempts=60] - Max polling attempts before timeout.
 * @param {function} [options.onStatus] - Optional callback called on each poll with the status string.
 * @returns {Promise<any>} Resolves with the task result on SUCCESS.
 */
export async function pollTask(taskId, { intervalMs = 1000, maxAttempts = 60, onStatus } = {}) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const data = await request(`/tasks/${taskId}`);
    if (onStatus) onStatus(data.status);

    if (data.status === "SUCCESS") {
      return data.result;
    }
    if (data.status === "FAILURE") {
      throw new Error(data.error || "Task failed");
    }
    // PENDING / STARTED / RETRY — wait and try again
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Task timed out after polling");
}

export const api = {
  getUsers: () => request("/users"),
  createUser: (payload) => request("/users", { method: "POST", body: JSON.stringify(payload) }),
  authToken: (payload) => request("/auth/token", { method: "POST", body: JSON.stringify(payload) }),
  authLoginOrRegister: (payload) => request("/auth/login-or-register", { method: "POST", body: JSON.stringify(payload) }),
  authVerify: (payload) => request("/auth/verify", { method: "POST", body: JSON.stringify(payload) }),
  authMe: () => request("/auth/me"),
  aiStatus: () => request("/ai/status"),

  listVocabularyMe: () => request("/vocabulary/me"),
  /** Returns { task_id, status, message } — use pollTask(task_id) to wait for the result. */
  addVocabularyMe: (payload) => request("/vocabulary/me", { method: "POST", body: JSON.stringify(payload) }),
  updateVocabularyMe: (itemId, payload) => request(`/vocabulary/me/${itemId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteVocabularyMe: (itemId) => request(`/vocabulary/me/${itemId}`, { method: "DELETE" }),

  /** Returns { task_id, status, message } — use pollTask(task_id) to wait for the result. */
  studyFlowCaptureToVocabularyMe: (payload) =>
    request("/study-flow/me/capture-to-vocabulary", { method: "POST", body: JSON.stringify(payload) }),

  reviewQueue: (limit = 20) => request(`/context/me/review-queue?limit=${limit}`),
  reviewStartSession: (payload) =>
    request("/context/me/review-session/start", { method: "POST", body: JSON.stringify(payload) }),
  reviewQueueSubmit: (payload) =>
    request("/context/me/review-queue/submit", { method: "POST", body: JSON.stringify(payload) }),

  reviewPlan: (limit = 10) => request(`/context/me/review-plan?limit=${limit}&horizon_hours=24`),
  cleanupContextGarbage: () => request("/context/me/cleanup-garbage", { method: "POST" }),
  reviewSummary: () => request("/analytics/review-summary/me"),

  translateMe: (payload) => request("/translate/me", { method: "POST", body: JSON.stringify(payload) }),
  /** Returns { task_id, status, message } — use pollTask(task_id) to wait for the result. */
  generateExercisesMe: (payload) => request("/exercises/me/generate", { method: "POST", body: JSON.stringify(payload) }),
  listSessionsMe: (params = {}) => request(`/sessions/me${toQuery(params)}`),
  listSessionAnswersMe: (sessionId) => request(`/sessions/me/${sessionId}/answers`),
  submitSession: (payload) => request("/sessions/submit", { method: "POST", body: JSON.stringify(payload) }),

  /** Poll a task by ID. */
  getTaskStatus: (taskId) => request(`/tasks/${taskId}`),
};
