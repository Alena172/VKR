function extractSentenceFromText(fullText, selectedText) {
  if (!fullText || !selectedText) {
    return "";
  }

  const normalizedFull = fullText.replace(/\s+/g, " ").trim();
  const normalizedSelected = selectedText.replace(/\s+/g, " ").trim();
  const idx = normalizedFull.toLowerCase().indexOf(normalizedSelected.toLowerCase());

  if (idx < 0) {
    return normalizedFull.slice(0, 500);
  }

  const left = normalizedFull.lastIndexOf(".", idx);
  const rightDot = normalizedFull.indexOf(".", idx + normalizedSelected.length);

  const start = left >= 0 ? left + 1 : 0;
  const end = rightDot >= 0 ? rightDot + 1 : Math.min(normalizedFull.length, idx + 250);

  return normalizedFull.slice(start, end).trim();
}

function getSelectionPayload() {
  const selectedText = window.getSelection()?.toString()?.trim() || "";
  let sourceSentence = "";

  try {
    const anchorNode = window.getSelection()?.anchorNode;
    const containerText = anchorNode?.textContent || "";
    sourceSentence = extractSentenceFromText(containerText, selectedText);
  } catch {
    sourceSentence = "";
  }

  return {
    selectedText,
    sourceSentence,
    sourceUrl: window.location.href,
    pageTitle: document.title,
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "VKR_GET_SELECTION") {
    sendResponse({ ok: true, payload: getSelectionPayload() });
    return true;
  }

  return false;
});
