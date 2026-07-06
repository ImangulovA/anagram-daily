// ===========================================================================
// GAME CONFIG — Anagram Daily.
//
// The platform (routing, timer, storage, stats, backend, archive, share) talks
// to your game ONLY through this object and the component's callback contract.
// ===========================================================================
import GameComponent from './GameComponent.svelte';
import { dayIndexes as dataDayIndexes, loadDay as dataLoadDay } from './data/days.js';
import { MAX_SCORE } from './scoring.js';

// Trim a score for display: integers print plain, halves get one decimal.
function trimNum(n) {
  if (typeof n !== 'number' || Number.isNaN(n)) return '—';
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

export const GAME = {
  // Storage namespace. MUST stay 'anagram' so the localStorage key is
  // `anagram_day<N>` — the exact key the games-hub reads and the original
  // static site wrote (existing player progress carries over).
  id: 'anagram',

  // Backend stats-worker "game" key. The live worker holds data under
  // 'anagram-daily', so we keep that (decoupled from `id` in platform/api.js).
  statsId: 'anagram-daily',

  title: 'Anagram Daily',
  tagline: 'Two clues, two words — anagram all their letters into a third.',

  // Day 0 = 5 July 2026 (monthIndex 6). Day N = this + N calendar days.
  anchorDate: [2026, 6, 5],

  component: GameComponent,

  dayIndexes: dataDayIndexes,
  loadDay: dataLoadDay,

  // Higher is better: the day's remaining points (0..20). The worker stores it
  // in tenths; /agg returns it back in points for the histogram.
  scoreOf(result) {
    return result && typeof result.score === 'number' ? result.score : null;
  },

  // Rich, spoiler-free share block. `result.marks` is precomputed at finish
  // time (clean solve / gave up / hint summary) by the scoring engine.
  shareLine(result, dayIdx, url) {
    const s = trimNum(result?.score);
    const max = result?.max ?? MAX_SCORE;
    const head = `${GAME.title} #${dayIdx} — ${s}/${max}`;
    return [head, result?.marks || '', url].filter(Boolean).join('\n');
  }
};
