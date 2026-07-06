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

  // Big celebratory emoji, keyed to how well you scored (out of 20). Shared by
  // the end screen and the Share text so they always match.
  //   0.5–10 → 👍   10–15 → 🎊   15–20 → 🐗🤯   (0 / gave up → nothing)
  resultEmoji(score) {
    if (typeof score !== 'number' || Number.isNaN(score)) return '';
    if (score >= 15) return '🐗🤯';
    if (score >= 10) return '🎊';
    if (score >= 0.5) return '👍';
    return '';
  },

  // Two-line, spoiler-free share:
  //   <url>
  //   #<day> -- <score>/<max> <celebration emoji> <hint-tally emojis>
  // `result.marks` is the emoji summary precomputed at finish time by the engine
  // (⭐ clean solve / 💀 gave up / 🟨🔤💡🎯🔍❌ hint tally).
  shareLine(result, dayIdx, url) {
    const s = trimNum(result?.score);
    const max = result?.max ?? MAX_SCORE;
    const emoji = this.resultEmoji(result?.score);
    const parts = [`#${dayIdx} -- ${s}/${max}`];
    if (emoji) parts.push(emoji);
    if (result?.marks) parts.push(result.marks);
    return `${url}\n${parts.join(' ')}`;
  }
};
