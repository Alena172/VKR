const API_BASE = "http://localhost:8000/api/v1";
const STORAGE_KEYS = {
  token: "vkrAuthToken",
  email: "vkrAuthEmail",
  userId: "vkrUserId",
};

const emailInput = document.getElementById("email");
const tokenInput = document.getElementById("token");
const userIdInput = document.getElementById("userId");
const selectedTextInput = document.getElementById("selectedText");
const sourceSentenceInput = document.getElementById("sourceSentence");
const output = document.getElementById("output");

const authTokenBtn = document.getElementById("authTokenBtn");
const clearTokenBtn = document.getElementById("clearTokenBtn");
const refreshSelectionBtn = document.getElementById("refreshSelection");
const translateBtn = document.getElementById("translateBtn");
const addBtn = document.getElementById("addBtn");

let currentToken = null;

function setOutput(data) {
  output.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function getUserId() {
  const value = Number(userIdInput.value);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function storageSet(data) {
  return new Promise((resolve) => chrome.storage.local.set(data, resolve));
}

function storageRemove(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, resolve));
}

async function requestJson(path, { method = "POST", payload = null } = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(currentToken ? { Authorization: `Bearer ${currentToken}` } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`);
  }

  return text ? JSON.parse(text) : null;
}

async function refreshIdentity() {
  if (!currentToken) {
    throw new Error("Сначала получи токен");
  }
  const identity = await requestJson("/auth/me", { method: "GET" });
  userIdInput.value = String(identity.user_id);
  await storageSet({ [STORAGE_KEYS.userId]: identity.user_id });
  return identity;
}

async function loadAuthState() {
  const stored = await storageGet([STORAGE_KEYS.token, STORAGE_KEYS.email, STORAGE_KEYS.userId]);
  currentToken = stored[STORAGE_KEYS.token] || null;
  if (stored[STORAGE_KEYS.email]) {
    emailInput.value = stored[STORAGE_KEYS.email];
  }
  if (currentToken) {
    tokenInput.value = currentToken;
  }
  if (stored[STORAGE_KEYS.userId]) {
    userIdInput.value = String(stored[STORAGE_KEYS.userId]);
  }
  if (currentToken) {
    refreshIdentity().catch((error) => {
      setOutput(`Ошибка токена: ${error.message}`);
    });
  }
}

async function issueToken() {
  const email = emailInput.value.trim();
  if (!email) {
    setOutput("Укажи email для получения токена");
    return;
  }

  try {
    const result = await requestJson("/auth/token", { method: "POST", payload: { email } });
    currentToken = result.access_token;
    tokenInput.value = currentToken;
    await storageSet({
      [STORAGE_KEYS.token]: currentToken,
      [STORAGE_KEYS.email]: email,
    });
    await refreshIdentity();
    setOutput({ status: "token_issued", user_id: getUserId() });
  } catch (error) {
    setOutput(`Ошибка получения токена: ${error.message}`);
  }
}

async function clearToken() {
  currentToken = null;
  tokenInput.value = "";
  userIdInput.value = "";
  await storageRemove([STORAGE_KEYS.token, STORAGE_KEYS.userId]);
  setOutput("Токен удален");
}

function requestSelectionFromTab() {
  return new Promise((resolve, reject) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs?.[0]?.id;
      if (!tabId) {
        reject(new Error("Активная вкладка не найдена"));
        return;
      }

      chrome.tabs.sendMessage(tabId, { type: "VKR_GET_SELECTION" }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (!response?.ok) {
          reject(new Error("Не удалось получить выделение"));
          return;
        }
        resolve(response.payload);
      });
    });
  });
}

async function refreshSelection() {
  try {
    const payload = await requestSelectionFromTab();
    selectedTextInput.value = payload.selectedText || "";
    sourceSentenceInput.value = payload.sourceSentence || "";
    setOutput({ status: "selection_loaded", pageTitle: payload.pageTitle, sourceUrl: payload.sourceUrl });
  } catch (error) {
    setOutput(`Ошибка выделения: ${error.message}`);
  }
}

async function translateSelection() {
  const text = selectedTextInput.value.trim();
  const sourceContext = sourceSentenceInput.value.trim();

  if (!currentToken) {
    setOutput("Сначала получи токен");
    return;
  }
  if (!text) {
    setOutput("Нет текста для перевода");
    return;
  }

  try {
    const result = await requestJson("/translate/me", {
      method: "POST",
      payload: {
        text,
        source_context: sourceContext || null,
      },
    });
    setOutput(result);
  } catch (error) {
    setOutput(`Ошибка перевода: ${error.message}`);
  }
}

async function addToVocabulary() {
  const selectedText = selectedTextInput.value.trim();
  const sourceSentence = sourceSentenceInput.value.trim();

  if (!currentToken) {
    setOutput("Сначала получи токен");
    return;
  }
  if (!selectedText) {
    setOutput("Нет выделенного текста для добавления");
    return;
  }

  try {
    const selection = await requestSelectionFromTab().catch(() => ({ sourceUrl: null }));
    const result = await requestJson("/vocabulary/me/from-capture", {
      method: "POST",
      payload: {
        selected_text: selectedText,
        source_sentence: sourceSentence || null,
        source_url: selection.sourceUrl || null,
        force_new_vocabulary_item: false,
      },
    });
    setOutput(result);
  } catch (error) {
    setOutput(`Ошибка добавления: ${error.message}`);
  }
}

authTokenBtn.addEventListener("click", issueToken);
clearTokenBtn.addEventListener("click", clearToken);
refreshSelectionBtn.addEventListener("click", refreshSelection);
translateBtn.addEventListener("click", translateSelection);
addBtn.addEventListener("click", addToVocabulary);

loadAuthState();
refreshSelection();

