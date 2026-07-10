// ---------------------------------------------------------------------------
// Thin client for the global-stats Worker. PLATFORM code. Every call is best-
// effort and silent: if STATS_API is '' (not deployed yet) or a request fails,
// we no-op so the game and local stats keep working.
//
// Two lifecycle events per day, each deduped server-side by (game, clientId,
// day, kind):
//   /start  — player began the day's game
//   /finish — player finished; carries active ms and an optional numeric score
// Plus /agg for the cross-player aggregates shown on the end/stats screens.
// ---------------------------------------------------------------------------
import { STATS_API } from '../config.js';
import { GAME } from '../game/index.js';

// Backend "game" key. Decoupled from GAME.id so the storage namespace (and thus
// the games-hub key `anagram_day<N>`) can stay 'anagram' while the stats worker
// keeps its existing 'anagram-daily' data. Falls back to GAME.id when unset.
const STATS_GAME = GAME.statsId || GAME.id;

const cidKey = () => `${GAME.id}_cid`;
const sentKey = (kind, day) => `${GAME.id}_sent_${kind}_day${day}`;

// A stable anonymous id, only to avoid double-counting server-side.
export function clientId() {
  if (typeof localStorage === 'undefined') return null;
  let id = localStorage.getItem(cidKey());
  if (!id) {
    id =
      (typeof crypto !== 'undefined' && crypto.randomUUID && crypto.randomUUID()) ||
      'c' + Math.random().toString(36).slice(2) + String(performance?.now?.() | 0);
    localStorage.setItem(cidKey(), id);
  }
  return id;
}

export const statsEnabled = () => !!STATS_API;

// CONFIRMED POST. Awaits the response and returns true ONLY when the Worker
// actually accepted the event, so a dropped request is never marked "sent" and
// gets retried on the next visit (Worker dedupes by clientId, so retries are
// safe). We use fetch with keepalive rather than navigator.sendBeacon: beacon
// returns true the instant the request is queued — NOT when it's delivered — so
// a silently dropped beacon looks like success. keepalive still lets the request
// survive a tab close, and our payloads are far under its 64KB cap.
//
// IMPORTANT: body is text/plain, NOT application/json. text/plain is a CORS-
// safelisted content type, so the cross-origin POST is a "simple request" with
// no preflight. The Worker parses with request.json() regardless.
async function post(path, payload) {
  if (!STATS_API || typeof fetch === 'undefined') return false;
  const url = STATS_API + path;
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify(payload),
      keepalive: true
    });
    return r.ok;
  } catch (e) {
    return false;
  }
}

// Mark a once-per-(kind,day) event as sent only after the Worker CONFIRMS it,
// so a transient failure backfills next visit (Worker dedupes by clientId).
async function once(kind, day, payload) {
  if (!STATS_API) return; // no backend yet -> don't mark, allow later backfill
  const hasLS = typeof localStorage !== 'undefined';
  if (hasLS && localStorage.getItem(sentKey(kind, day))) return;
  const ok = await post('/' + kind, { game: STATS_GAME, day, clientId: clientId(), ...payload });
  if (ok && hasLS) localStorage.setItem(sentKey(kind, day), '1');
}

export function submitStart(day) {
  return once('start', day, {});
}

export function submitFinish(day, ms, score) {
  return once('finish', day, {
    ms: Math.round(ms || 0),
    score: typeof score === 'number' ? score : null
  });
}

// Fetch aggregates for the given day indexes. Returns null on failure.
export async function fetchAgg(days) {
  if (!STATS_API || typeof fetch === 'undefined') return null;
  try {
    const q = encodeURIComponent((days || []).join(','));
    const r = await fetch(`${STATS_API}/agg?game=${encodeURIComponent(STATS_GAME)}&days=${q}`);
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}
