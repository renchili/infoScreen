"use strict";

const SESSION_PREFIX = "infoscreen-local-event-feedback:";

function sessionKey(tabId) {
  return `${SESSION_PREFIX}${tabId}`;
}

function storageGet(key) {
  return new Promise((resolve) => {
    chrome.storage.session.get(key, (value) => resolve(value[key] || null));
  });
}

function storageSet(key, value) {
  return new Promise((resolve, reject) => {
    chrome.storage.session.set({ [key]: value }, () => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve();
    });
  });
}

function storageRemove(key) {
  return new Promise((resolve) => chrome.storage.session.remove(key, resolve));
}

function createTab(properties) {
  return new Promise((resolve, reject) => {
    chrome.tabs.create(properties, (tab) => {
      if (chrome.runtime.lastError || !tab?.id) {
        reject(new Error(chrome.runtime.lastError?.message || "Unable to create browser tab"));
      } else {
        resolve(tab);
      }
    });
  });
}

function updateTab(tabId, properties) {
  return new Promise((resolve, reject) => {
    chrome.tabs.update(tabId, properties, (tab) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(tab);
    });
  });
}

function encodeFeedback(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function validSession(raw) {
  if (!raw || typeof raw !== "object") throw new Error("Feedback session is missing");
  const surfaceOrigin = String(raw.surface_origin || "").replace(/\/$/, "");
  const listingUrl = String(raw.listing_url || "");
  const sourceId = String(raw.source_id || "").trim();
  if (!/^https?:\/\//i.test(surfaceOrigin)) throw new Error("Surface URL is invalid");
  if (!/^https?:\/\//i.test(listingUrl)) throw new Error("Listing URL is invalid");
  if (!sourceId) throw new Error("Institution is missing");
  return {
    surface_origin: surfaceOrigin,
    source_id: sourceId,
    listing_url: listingUrl,
    created_at: new Date().toISOString(),
  };
}

async function startFeedback(rawSession) {
  const session = validSession(rawSession);
  const tab = await createTab({ url: "about:blank", active: true });
  await storageSet(sessionKey(tab.id), session);
  await updateTab(tab.id, { url: session.listing_url });
  return { ok: true, tab_id: tab.id };
}

async function submitFeedback(tabId, payload) {
  const session = await storageGet(sessionKey(tabId));
  if (!session) throw new Error("Feedback session expired. Start it again from InfoScreen.");

  const feedback = {
    ...payload,
    source_id: session.source_id,
    listing_url: session.listing_url,
  };
  const response = await fetch(`${session.surface_origin}/api/local-events/review/open-feedback`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_id: session.source_id,
      listing_url: `feedback:${encodeFeedback(feedback)}`,
    }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) {
    throw new Error(result.detail || result.error || `HTTP ${response.status}`);
  }
  return { ok: true, result };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const type = String(message?.type || "");

  if (type === "startFeedback") {
    startFeedback(message.session)
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }

  if (type === "getFeedbackSession") {
    const tabId = sender.tab?.id;
    if (!tabId) {
      sendResponse({ ok: true, session: null });
      return false;
    }
    storageGet(sessionKey(tabId))
      .then((session) => sendResponse({ ok: true, session }))
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }

  if (type === "submitFeedback") {
    const tabId = sender.tab?.id;
    if (!tabId) {
      sendResponse({ ok: false, error: "Browser tab is unavailable" });
      return false;
    }
    submitFeedback(tabId, message.payload || {})
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }

  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  storageRemove(sessionKey(tabId));
});
