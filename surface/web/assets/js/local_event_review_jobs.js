"use strict";

(() => {
  const COLLECTION_PATH = "/api/local-events/review/collect-events";
  const STATE_PATH = "/api/local-events/review/state";
  const originalFetch = window.fetch.bind(window);
  let activeJobId = "";
  let activePoll = null;

  const sleep = (milliseconds) => new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });

  function jobFrom(payload) {
    return payload?.event_collection_job
      || payload?.event_collection?.background_job
      || null;
  }

  function ensureProgress() {
    let node = document.getElementById("event-collection-job");
    if (node) return node;

    node = document.createElement("div");
    node.id = "event-collection-job";
    node.className = "review-job-progress";
    node.hidden = true;
    node.innerHTML = `
      <div class="review-job-progress-head">
        <strong id="event-collection-job-title">BACKGROUND EVENT COLLECTION</strong>
        <span id="event-collection-job-elapsed">0s</span>
      </div>
      <div id="event-collection-job-message" class="review-job-progress-message"></div>
      <div id="event-collection-job-result" class="review-job-progress-result"></div>`;

    const toolbar = document.querySelector(".toolbar");
    if (toolbar) toolbar.insertAdjacentElement("afterend", node);
    else document.querySelector("main")?.prepend(node);
    return node;
  }

  function updateUi(job) {
    if (!job) return;
    const running = job.status === "running";
    const node = ensureProgress();
    node.hidden = job.status === "idle";
    node.dataset.status = job.status || "idle";

    const elapsed = Number(job.elapsed_seconds || 0);
    const title = document.getElementById("event-collection-job-title");
    const elapsedNode = document.getElementById("event-collection-job-elapsed");
    const message = document.getElementById("event-collection-job-message");
    const result = document.getElementById("event-collection-job-result");
    const status = document.getElementById("global-status");
    const collectButton = document.getElementById("collect-events");

    if (title) {
      title.textContent = running
        ? "BACKGROUND EVENT COLLECTION RUNNING"
        : job.status === "completed"
          ? "BACKGROUND EVENT COLLECTION COMPLETE"
          : "BACKGROUND EVENT COLLECTION FAILED";
    }
    if (elapsedNode) elapsedNode.textContent = `${elapsed}s`;
    if (message) message.textContent = job.message || job.stage || "";
    if (result) {
      const parts = [];
      if (job.candidate_count != null) parts.push(`candidates ${Number(job.candidate_count || 0)}`);
      if (job.confirmed_listing_count != null) parts.push(`list pages ${Number(job.confirmed_listing_count || 0)}`);
      if (job.error_count) parts.push(`errors ${Number(job.error_count || 0)}`);
      result.textContent = parts.join(" · ");
    }
    if (collectButton) collectButton.disabled = running;
    if (status && running) {
      status.textContent = `COLLECTING IN BACKGROUND · ${elapsed}s`;
      status.className = "status warn";
    }

    document.dispatchEvent(new CustomEvent("infoscreen:review-job", {
      detail: job,
    }));
  }

  async function readState() {
    const response = await originalFetch(STATE_PATH, { cache: "no-store" });
    const payload = await response.json().catch(async () => ({
      ok: false,
      error: await response.text(),
    }));
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  async function pollJob(jobId) {
    while (true) {
      const state = await readState();
      const job = jobFrom(state);
      if (!job || !job.job_id) {
        throw new Error("Background Event collection status disappeared");
      }
      if (jobId && job.job_id !== jobId && job.status === "running") {
        throw new Error("A different Event collection job is running");
      }

      updateUi(job);
      if (job.status === "completed") return state;
      if (job.status === "failed") {
        throw new Error(job.message || "Event candidate collection failed");
      }
      await sleep(1000);
    }
  }

  function sharedPoll(jobId) {
    if (activePoll && activeJobId === jobId) return activePoll;
    activeJobId = jobId;
    activePoll = pollJob(jobId).finally(() => {
      activePoll = null;
      activeJobId = "";
    });
    return activePoll;
  }

  function responseFrom(payload, status = 200) {
    return new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }

  window.fetch = async (input, init = {}) => {
    const raw = typeof input === "string" ? input : input?.url || "";
    const path = new URL(raw, window.location.href).pathname;
    const method = String(
      init.method || (typeof input !== "string" ? input?.method : "GET") || "GET",
    ).toUpperCase();

    if (path !== COLLECTION_PATH || method !== "POST") {
      return originalFetch(input, init);
    }

    const response = await originalFetch(input, init);
    const payload = await response.clone().json().catch(() => ({}));
    if (!response.ok) return response;

    const job = jobFrom(payload);
    if (!job || job.status !== "running" || !job.job_id) return response;
    updateUi(job);

    try {
      const completedState = await sharedPoll(job.job_id);
      return responseFrom(completedState, 200);
    } catch (error) {
      return responseFrom({
        ok: false,
        error: "event_candidate_collection_failed",
        detail: String(error?.message || error),
      }, 500);
    }
  };

  async function resumeRunningJob() {
    try {
      const state = await readState();
      const job = jobFrom(state);
      updateUi(job);
      if (!job || job.status !== "running" || !job.job_id) return;
      await sharedPoll(job.job_id);
      document.getElementById("reload-state")?.click();
    } catch (error) {
      const status = document.getElementById("global-status");
      if (status) {
        status.textContent = String(error?.message || error);
        status.className = "status error";
      }
    }
  }

  document.addEventListener("DOMContentLoaded", resumeRunningJob);
})();
