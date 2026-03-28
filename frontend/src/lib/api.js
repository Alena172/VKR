const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const AUTH_TOKEN_KEY = "vkr_auth_token";

export function setAuthToken(token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function isAbortError(error) {
  return error?.name === "AbortError";
}

function getErrorDetail(payload, fallbackText) {
  if (typeof payload?.detail === "string" && payload.detail.trim()) {
    return payload.detail.trim();
  }
  if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
    return payload.detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (typeof item?.msg === "string") {
          return item.msg;
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (typeof fallbackText === "string" && fallbackText.trim()) {
    return fallbackText.trim();
  }
  return "";
}

function buildUserMessage(status, detail) {
  if (detail) {
    return detail;
  }
  if (status === 401) {
    return "Нужно заново войти в систему.";
  }
  if (status === 403) {
    return "Недостаточно прав для этого действия.";
  }
  if (status === 404) {
    return "Запрошенные данные не найдены.";
  }
  if (status === 422) {
    return "Проверьте введенные данные.";
  }
  if (status >= 500) {
    return "Сервер временно недоступен. Попробуйте еще раз.";
  }
  if (status > 0) {
    return `Ошибка запроса (${status}).`;
  }
  return "Не удалось выполнить запрос. Проверьте сеть и попробуйте еще раз.";
}

function createApiError({ status, detail = "", raw = null }) {
  const userMessage = buildUserMessage(status, detail);
  const error = new Error(userMessage);
  error.name = "ApiError";
  error.status = status;
  error.detail = detail || null;
  error.userMessage = userMessage;
  error.raw = raw;
  return error;
}

export function getErrorMessage(error) {
  if (!error) {
    return "Произошла неизвестная ошибка.";
  }
  return error.userMessage || error.message || "Произошла неизвестная ошибка.";
}

function sleep(ms, signal) {
  if (signal?.aborted) {
    return Promise.reject(new DOMException("The operation was aborted.", "AbortError"));
  }
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);

    const onAbort = () => {
      clearTimeout(timeoutId);
      signal?.removeEventListener("abort", onAbort);
      reject(new DOMException("The operation was aborted.", "AbortError"));
    };

    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function request(path, options = {}) {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw createApiError({
      status: 0,
      detail: "",
      raw: error,
    });
  }

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let raw = null;
    let payload = null;
    let text = "";

    try {
      if (contentType.includes("application/json")) {
        payload = await response.json();
        raw = payload;
      } else {
        text = await response.text();
        raw = text;
      }
    } catch {
      text = "";
    }

    throw createApiError({
      status: response.status,
      detail: getErrorDetail(payload, text),
      raw,
    });
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

export async function pollTask(
  taskId,
  {
    intervalMs = 1000,
    maxAttempts = 60,
    maxIntervalMs = 5000,
    backoffFactor = 1.35,
    onStatus,
    signal,
  } = {},
) {
  let currentIntervalMs = intervalMs;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    const data = await request(`/tasks/${taskId}`, { signal });
    if (onStatus) {
      onStatus(data.status);
    }

    if (data.status === "SUCCESS") {
      return data.result;
    }
    if (data.status === "FAILURE") {
      throw createApiError({
        status: 500,
        detail: data.error || "Task failed",
        raw: data,
      });
    }

    if (attempt < maxAttempts - 1) {
      await sleep(currentIntervalMs, signal);
      currentIntervalMs = Math.min(maxIntervalMs, Math.round(currentIntervalMs * backoffFactor));
    }
  }

  throw createApiError({
    status: 408,
    detail: "Task timed out after polling",
    raw: { taskId, maxAttempts },
  });
}

export const api = {
  getUsers: (options = {}) => request("/users", options),
  createUser: (payload, options = {}) => request("/users", { method: "POST", body: JSON.stringify(payload), ...options }),
  authToken: (payload, options = {}) => request("/auth/token", { method: "POST", body: JSON.stringify(payload), ...options }),
  authLoginOrRegister: (payload, options = {}) =>
    request("/auth/login-or-register", { method: "POST", body: JSON.stringify(payload), ...options }),
  authVerify: (payload, options = {}) => request("/auth/verify", { method: "POST", body: JSON.stringify(payload), ...options }),
  authMe: (options = {}) => request("/auth/me", options),
  aiStatus: (options = {}) => request("/ai/status", options),

  listVocabularyMe: (options = {}) => request("/vocabulary/me", options),
  addVocabularyMe: (payload, options = {}) => request("/vocabulary/me", { method: "POST", body: JSON.stringify(payload), ...options }),
  updateVocabularyMe: (itemId, payload, options = {}) =>
    request(`/vocabulary/me/${itemId}`, { method: "PUT", body: JSON.stringify(payload), ...options }),
  deleteVocabularyMe: (itemId, options = {}) => request(`/vocabulary/me/${itemId}`, { method: "DELETE", ...options }),

  studyFlowCaptureToVocabularyMe: (payload, options = {}) =>
    request("/vocabulary/me/from-capture", { method: "POST", body: JSON.stringify(payload), ...options }),

  reviewQueue: (limit = 20, options = {}) => request(`/context/me/review-queue?limit=${limit}`, options),
  reviewStartSession: (payload, options = {}) =>
    request("/context/me/review-session/start", { method: "POST", body: JSON.stringify(payload), ...options }),
  reviewQueueSubmit: (payload, options = {}) =>
    request("/context/me/review-queue/submit", { method: "POST", body: JSON.stringify(payload), ...options }),

  reviewPlan: (limit = 10, options = {}) => request(`/context/me/review-plan?limit=${limit}&horizon_hours=24`, options),
  cleanupContextGarbage: (options = {}) => request("/context/me/cleanup-garbage", { method: "POST", ...options }),
  reviewSummary: (options = {}) => request("/context/me/review-summary", options),
  learningGraphRecommendations: (mode = "mixed", limit = 10, options = {}) =>
    request(`/learning-graph/me/recommendations?mode=${encodeURIComponent(mode)}&limit=${limit}`, options),
  learningGraphAnchors: (englishLemma, limit = 5, options = {}) =>
    request(`/learning-graph/me/anchors?english_lemma=${encodeURIComponent(englishLemma)}&limit=${limit}`, options),
  learningGraphObservability: (options = {}) => request("/learning-graph/me/observability", options),

  translateMe: (payload, options = {}) => request("/translate/me", { method: "POST", body: JSON.stringify(payload), ...options }),
  generateExercisesMe: (payload, options = {}) =>
    request("/exercises/me/generate", { method: "POST", body: JSON.stringify(payload), ...options }),
  listSessionsMe: (params = {}, options = {}) => request(`/sessions/me${toQuery(params)}`, options),
  listSessionAnswersMe: (sessionId, options = {}) => request(`/sessions/me/${sessionId}/answers`, options),
  submitSession: (payload, options = {}) => request("/sessions/submit", { method: "POST", body: JSON.stringify(payload), ...options }),

  getTaskStatus: (taskId, options = {}) => request(`/tasks/${taskId}`, options),
};
