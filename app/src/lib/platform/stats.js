// ---------------------------------------------------------------------------
// Personal stats across all days, from localStorage. PLATFORM code, game-
// agnostic: metrics are started / finished / time / streaks. A game's own score
// (if any) is pulled through GAME.scoreOf(result) so scored and unscored games
// both work. Global cross-player numbers come from the Worker (api.js).
// ---------------------------------------------------------------------------
import { GAME } from '../game/index.js';
import { loadAll } from './storage.js';
import { currentDay } from './days.js';

export function computeStats(now = new Date()) {
  if (typeof localStorage === 'undefined') return null; // SSR / prerender

  const records = loadAll();
  const entries = {};
  for (const idxStr of Object.keys(records)) {
    const idx = Number(idxStr);
    const r = records[idx];
    if (!r.started) continue; // never opened -> not a "play"
    entries[idx] = {
      idx,
      started: true,
      finished: !!r.finished,
      live: r.live === true,
      ms: r.elapsedMs || 0,
      score: r.finished ? scoreSafe(r.result) : null
    };
  }

  const startedIdx = Object.values(entries)
    .map((e) => e.idx)
    .sort((a, b) => a - b);
  const finishedIdx = Object.values(entries)
    .filter((e) => e.finished)
    .map((e) => e.idx)
    .sort((a, b) => a - b);
  const finishedSet = new Set(finishedIdx);

  // longest run of consecutive finished day indexes
  let maxStreak = 0;
  let run = 0;
  let prev = null;
  for (const idx of finishedIdx) {
    run = prev !== null && idx === prev + 1 ? run + 1 : 1;
    if (run > maxStreak) maxStreak = run;
    prev = idx;
  }

  // current streak: count back from today (grace: if today isn't finished yet,
  // anchor on yesterday so the streak survives until a full day is missed).
  const cur = currentDay(now);
  let anchorIdx = finishedSet.has(cur) ? cur : cur - 1;
  let currentStreak = 0;
  while (finishedSet.has(anchorIdx)) {
    currentStreak += 1;
    anchorIdx -= 1;
  }

  const fin = finishedIdx.map((i) => entries[i]);
  const times = fin.map((e) => e.ms).filter((m) => m > 0);
  const scores = fin.map((e) => e.score).filter((s) => typeof s === 'number');

  const liveCount = fin.filter((e) => e.live).length;
  const sum = (arr) => arr.reduce((s, x) => s + x, 0);

  return {
    started: startedIdx.length,
    finished: fin.length,
    finishRate: startedIdx.length ? fin.length / startedIdx.length : 0,
    onDate: liveCount,
    later: fin.length - liveCount,
    currentStreak,
    maxStreak,
    avgMs: times.length ? sum(times) / times.length : 0,
    bestMs: times.length ? Math.min(...times) : 0,
    scored: scores.length > 0,
    avgScore: scores.length ? sum(scores) / scores.length : null,
    bestScore: scores.length ? Math.max(...scores) : null,
    days: fin
      .map((e) => ({ idx: e.idx, ms: e.ms, score: e.score, live: e.live }))
      .sort((a, b) => a.idx - b.idx),
    startedIdx,
    finishedIdx
  };
}

function scoreSafe(result) {
  try {
    const s = GAME.scoreOf ? GAME.scoreOf(result) : null;
    return typeof s === 'number' ? s : null;
  } catch (e) {
    return null;
  }
}
