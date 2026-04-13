/**
 * api.js — Plugify frontend ↔ Flask backend bridge
 *
 * All fetch calls live here. The UI never talks to the backend directly.
 * Change the base URL once here and everything updates.
 */

const BASE_URL = "http://127.0.0.1:5000";   // change to your deployed URL in production

/**
 * Search for extensions by natural language query.
 * @param {string} query
 * @returns {Promise<{ query, intent, results, meta }>}
 */
export async function searchExtensions(query) {
  const res = await fetch(`${BASE_URL}/api/recommend`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ query }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Server error ${res.status}`);
  }
  return res.json();
}

/**
 * Log a user interaction (click, thumbs up/down).
 * Fire-and-forget — UI doesn't need to await this.
 * @param {{ query, chosen_id, position, feedback_type, session_id? }} payload
 */
export function logFeedback(payload) {
  fetch(`${BASE_URL}/api/feedback`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  }).catch(err => console.warn("Feedback log failed:", err));
}
