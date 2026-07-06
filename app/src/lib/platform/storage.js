// ---------------------------------------------------------------------------
// Per-day persistence in localStorage. PLATFORM code — game-agnostic.
//
// One record per day index, keyed `<GAME.id>_day<N>`:
//   {
//     started:    bool,        // player has interacted at least once
//     finished:   bool,        // game reported a final result
//     startedAt:  ms epoch,    // first interaction
//     finishedAt: ms epoch|null,
//     elapsedMs:  number,      // accumulated ACTIVE play time (timer.js)
//     live:       bool,        // played on the puzzle's own calendar date
//     state:      any|null,    // opaque resume blob the game hands us
//     result:     any|null     // opaque final-result blob the game hands us
//   }
//
// The platform never inspects `state`/`result`; only the GAME module does
// (via GAME.scoreOf / GAME.shareLine). This keeps storage reusable for any game.
// ---------------------------------------------------------------------------
import { GAME } from '../game/index.js';

const key = (idx) => `${GAME.id}_day${idx}`;

const EMPTY = {
  started: false,
  finished: false,
  startedAt: null,
  finishedAt: null,
  elapsedMs: 0,
  live: false,
  state: null,
  result: null
};

export function loadDay(idx) {
  if (typeof localStorage === 'undefined') return { ...EMPTY };
  try {
    const raw = localStorage.getItem(key(idx));
    if (!raw) return { ...EMPTY };
    return { ...EMPTY, ...JSON.parse(raw) };
  } catch (e) {
    return { ...EMPTY };
  }
}

export function saveDay(idx, record) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(key(idx), JSON.stringify(record));
  } catch (e) {
    /* quota / private mode — ignore, game keeps working in memory */
  }
}

// Read every saved day record (used by stats.js / archive). Returns a map
// { idx: record } only for days that have data AND a saved record.
export function loadAll() {
  const out = {};
  if (typeof localStorage === 'undefined') return out;
  for (const idx of GAME.dayIndexes()) {
    const raw = (() => {
      try {
        return localStorage.getItem(key(idx));
      } catch (e) {
        return null;
      }
    })();
    if (raw) out[idx] = loadDay(idx);
  }
  return out;
}
