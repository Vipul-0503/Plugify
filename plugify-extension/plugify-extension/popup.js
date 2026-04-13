/**
 * popup.js — Plugify Chrome Extension
 * ------------------------------------
 * Handles all interaction in the extension popup:
 *   - Sending queries to the Flask backend
 *   - Rendering extension cards
 *   - Logging feedback (clicks, thumbs)
 *   - Persisting recent searches via chrome.storage
 */

const BASE_URL = "http://127.0.0.1:5000";

// ── DOM references ──
const queryInput  = document.getElementById("query-input");
const sendBtn     = document.getElementById("send-btn");
const resultsArea = document.getElementById("results-area");
const welcome     = document.getElementById("welcome");
const statusDot   = document.getElementById("status-dot");
const offlineNote = document.getElementById("offline-notice");

// ── State ──
let isSearching = false;
let lastQuery   = "";

// ─────────────────────────────────────────────
// Startup: check backend health + load history
// ─────────────────────────────────────────────
async function init() {
  await checkHealth();
  loadSuggestionChips();
}

async function checkHealth() {
  try {
    const res = await fetch(`${BASE_URL}/api/health`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      statusDot.classList.remove("offline");
      statusDot.title = "Backend connected";
      offlineNote.classList.remove("show");
    } else {
      throw new Error("unhealthy");
    }
  } catch {
    statusDot.classList.add("offline");
    statusDot.title = "Backend offline";
    offlineNote.classList.add("show");
  }
}

// ─────────────────────────────────────────────
// Suggestion chips — clickable shortcuts
// ─────────────────────────────────────────────
function loadSuggestionChips() {
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.query;
      queryInput.value = q;
      handleSearch();
    });
  });
}

// ─────────────────────────────────────────────
// Input handling
// ─────────────────────────────────────────────
queryInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSearch();
  }
});

queryInput.addEventListener("input", () => {
  queryInput.style.height = "auto";
  queryInput.style.height = Math.min(queryInput.scrollHeight, 100) + "px";
});

sendBtn.addEventListener("click", handleSearch);

// ─────────────────────────────────────────────
// Main search function
// ─────────────────────────────────────────────
async function handleSearch() {
  if (isSearching) return;

  const query = queryInput.value.trim();
  if (!query) return;

  isSearching    = true;
  sendBtn.disabled = true;
  lastQuery      = query;

  // Hide welcome, show loader
  hideWelcome();
  showLoading();

  try {
    const res = await fetch(`${BASE_URL}/api/recommend`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ query }),
      signal:  AbortSignal.timeout(15000),
    });

    if (!res.ok) throw new Error(`Server error ${res.status}`);

    const data = await res.json();
    renderResults(data);
    saveRecentQuery(query);

  } catch (err) {
    showError(err);
  } finally {
    isSearching      = false;
    sendBtn.disabled = false;
  }
}

// ─────────────────────────────────────────────
// Render results
// ─────────────────────────────────────────────
function renderResults(data) {
  const { results = [], intent = {} } = data;

  let html = "";

  // Intent badge
  if (intent.category && intent.category !== "general") {
    const label = intent.category.charAt(0).toUpperCase() + intent.category.slice(1);
    html += `<div class="intent-badge">🎯 ${label}</div>`;
  }

  if (!results.length) {
    html += `
      <div class="error-box">
        <div class="err-title">No matches found</div>
        <div class="err-sub">Try rephrasing — describe the problem, not the feature name</div>
      </div>`;
    resultsArea.innerHTML = html;
    return;
  }

  html += `<div class="results-count">${results.length} underrated extensions matched</div>`;

  results.forEach((ext, index) => {
    html += buildCard(ext, index);
  });

  resultsArea.innerHTML = html;

  // Attach open-button listeners after render
  resultsArea.querySelectorAll(".open-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const { extId, position, link } = btn.dataset;
      logFeedback(lastQuery, extId, parseInt(position), "click");
      chrome.tabs.create({ url: link });
    });
  });

  // Attach thumbs listeners
  resultsArea.querySelectorAll(".thumb-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const { extId, position, type } = btn.dataset;
      logFeedback(lastQuery, extId, parseInt(position), type);
      btn.style.opacity = "1";
      btn.style.color   = type === "thumbs_up" ? "#4ade80" : "#fb7c6e";
      // Disable both thumb buttons for this card after rating
      btn.closest(".ext-card")
        .querySelectorAll(".thumb-btn")
        .forEach(b => b.disabled = true);
    });
  });
}

// ─────────────────────────────────────────────
// Build a single extension card HTML
// ─────────────────────────────────────────────
function buildCard(ext, index) {
  const matchPct    = Math.round((ext.score || 0) * 180);
  const isGem       = (ext.installs || 0) < 30000;
  const installs    = ext.installs >= 1000
    ? `${Math.round(ext.installs / 1000)}k`
    : ext.installs || "—";
  const explanation = ext.explanation || "";

  return `
    <div class="ext-card">
      <div class="ext-card-top">
        <div class="ext-left">
          <div class="ext-icon">${ext.icon || "🧩"}</div>
          <div>
            <div class="ext-name">${escHtml(ext.name)}</div>
            <div class="ext-pills">
              <span class="pill pill-cat">${escHtml(ext.category || "")}</span>
              ${isGem ? '<span class="pill pill-gem">hidden gem</span>' : ""}
              <span class="pill pill-match">${matchPct}% match</span>
            </div>
          </div>
        </div>
        <div class="ext-score">
          <div class="score-num">${(ext.rating || 0).toFixed(1)}</div>
          <div class="score-label">rating</div>
        </div>
      </div>

      <div class="ext-desc">${escHtml(ext.description || ext.desc || "")}</div>

      ${explanation ? `<div class="ext-explanation">${explanation}</div>` : ""}

      <div class="ext-footer">
        <div class="ext-stats">
          <span class="stat">👥 <span class="stat-val">${installs}</span></span>
          <span class="stat">⭐ <span class="stat-val">${(ext.rating || 0).toFixed(1)}</span></span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <button class="thumb-btn"
            style="background:none;border:none;cursor:pointer;font-size:13px;opacity:0.5;color:var(--text2)"
            data-ext-id="${ext.id}"
            data-position="${index}"
            data-type="thumbs_up"
            title="Good result">👍</button>
          <button class="thumb-btn"
            style="background:none;border:none;cursor:pointer;font-size:13px;opacity:0.5;color:var(--text2)"
            data-ext-id="${ext.id}"
            data-position="${index}"
            data-type="thumbs_down"
            title="Poor result">👎</button>
          <a class="open-btn"
            data-ext-id="${ext.id}"
            data-position="${index}"
            data-link="${escHtml(ext.link || "")}"
            href="#">
            Open in Store
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" stroke-width="2">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
        </div>
      </div>
    </div>
  `;
}

// ─────────────────────────────────────────────
// Feedback logger
// ─────────────────────────────────────────────
function logFeedback(query, chosenId, position, feedbackType) {
  fetch(`${BASE_URL}/api/feedback`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      query,
      chosen_id:     chosenId,
      position,
      feedback_type: feedbackType,
    }),
  }).catch(() => {}); // fire-and-forget — never block UI
}

// ─────────────────────────────────────────────
// Recent queries via chrome.storage.local
// ─────────────────────────────────────────────
function saveRecentQuery(query) {
  chrome.storage.local.get(["recentQueries"], ({ recentQueries = [] }) => {
    const updated = [query, ...recentQueries.filter(q => q !== query)].slice(0, 5);
    chrome.storage.local.set({ recentQueries: updated });
  });
}

// ─────────────────────────────────────────────
// UI state helpers
// ─────────────────────────────────────────────
function hideWelcome() {
  if (welcome) welcome.style.display = "none";
}

function showLoading() {
  resultsArea.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      <div class="loading-text">Searching for underrated gems…</div>
    </div>
  `;
}

function showError(err) {
  const isNetwork = err.name === "TypeError" || err.name === "TimeoutError";
  resultsArea.innerHTML = `
    <div class="error-box">
      <div class="err-title">${isNetwork ? "Cannot reach backend" : "Something went wrong"}</div>
      <div class="err-sub">${isNetwork
        ? "Make sure python run.py is running on port 5000"
        : escHtml(err.message)
      }</div>
    </div>
  `;
}

// ─────────────────────────────────────────────
// Utility: escape HTML to prevent XSS
// ─────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────
init();
