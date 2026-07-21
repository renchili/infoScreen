"use strict";

(() => {
  const READY = "infoscreen-local-event-feedback-extension-ready";
  const PING = "infoscreen-local-event-feedback-extension-ping";
  const START = "infoscreen-local-event-feedback-start";
  const STARTED = "infoscreen-local-event-feedback-started";
  let extensionReady = false;
  let startTimer = 0;

  const byId = (id) => document.getElementById(id);
  const text = (value) => String(value || "").trim();

  function setStatus(message, kind = "") {
    const node = byId("feedback-status");
    if (!node) return;
    node.textContent = message;
    node.className = `status ${kind}`.trim();
  }

  function setMessage(message) {
    const node = byId("feedback-message");
    if (node) node.textContent = message;
  }

  function helperInstructions() {
    return "The browser helper is not installed on this device. Download it, extract the ZIP, open chrome://extensions, enable Developer mode, choose Load unpacked, and select the extracted folder. Then reload this page.";
  }

  function replaceOpenButton() {
    const original = byId("open-feedback-browser");
    if (!original || original.dataset.remoteDevice === "true") return;

    const button = original.cloneNode(true);
    button.dataset.remoteDevice = "true";
    button.textContent = "OPEN ON THIS DEVICE";
    button.addEventListener("click", () => {
      const sourceId = text(byId("feedback-source")?.value);
      const listingUrl = text(byId("feedback-listing")?.value);
      if (!sourceId || !listingUrl) {
        setStatus("SELECT A LISTING PAGE", "error");
        return;
      }
      if (!extensionReady) {
        setStatus("BROWSER HELPER NOT INSTALLED", "error");
        setMessage(helperInstructions());
        return;
      }

      button.disabled = true;
      setStatus("OPENING ON THIS DEVICE", "warn");
      setMessage("Opening the official listing in this browser. The Surface display is not used.");
      window.clearTimeout(startTimer);
      startTimer = window.setTimeout(() => {
        button.disabled = false;
        setStatus("BROWSER HELPER DID NOT RESPOND", "error");
        setMessage("Reload this page and verify that the InfoScreen Local Event Feedback extension is enabled in this browser.");
      }, 5000);

      window.postMessage({
        type: START,
        session: {
          surface_origin: window.location.origin,
          source_id: sourceId,
          listing_url: listingUrl,
        },
      }, "*");
    });
    original.replaceWith(button);
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window || !event.data || typeof event.data !== "object") return;
    if (event.data.type === READY) {
      extensionReady = true;
      const button = byId("open-feedback-browser");
      if (button) button.title = `Browser helper ${text(event.data.version) || "ready"}`;
      if (text(byId("feedback-status")?.textContent) === "BROWSER HELPER NOT INSTALLED") {
        setStatus("READY", "ok");
        setMessage("The helper is ready. OPEN ON THIS DEVICE will use this browser, not the Surface screen.");
      }
      return;
    }
    if (event.data.type !== STARTED) return;

    window.clearTimeout(startTimer);
    const button = byId("open-feedback-browser");
    if (button) button.disabled = false;
    if (event.data.ok) {
      setStatus("OPENED ON THIS DEVICE", "ok");
      setMessage("Browse normally in the new tab. Click POINT TO EVENT only when the Event card is visible, then submit its position.");
    } else {
      setStatus("FAILED", "error");
      setMessage(text(event.data.error) || "The browser helper could not open the listing page.");
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) byId("reload-state")?.click();
  });

  document.addEventListener("DOMContentLoaded", () => {
    replaceOpenButton();
    window.postMessage({ type: PING }, "*");
    window.setTimeout(() => {
      if (!extensionReady) {
        setMessage("This workflow runs in the browser on the device you are using now. Install the Chrome helper once; it does not open Chromium on the Surface.");
      }
    }, 800);
  });
})();
