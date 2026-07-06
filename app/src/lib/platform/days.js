// ---------------------------------------------------------------------------
// Day numbering: maps calendar dates <-> day indexes. PLATFORM code — do not
// edit per fork. The anchor date and the list of available days come from the
// GAME config (../game/index.js), so this file stays game-agnostic.
//
// Day 0 = GAME.anchorDate. One puzzle-day per calendar day. Indexes can be
// negative (an "exception" day before the anchor, handy for pre-launch tests).
// ---------------------------------------------------------------------------
import { GAME } from '../game/index.js';

const MS_PER_DAY = 24 * 60 * 60 * 1000;

// GAME.anchorDate is [year, monthIndex(0-11), day]; build a LOCAL-midnight Date.
function anchor() {
  const [y, m, d] = GAME.anchorDate;
  return new Date(y, m, d);
}

// Local-midnight Date for a given day index.
export function dateForDay(idx, base = anchor()) {
  return new Date(base.getTime() + idx * MS_PER_DAY);
}

// Today's day index (floored to local midnight to avoid DST drift).
export function todayIndex(now = new Date()) {
  const a = anchor();
  const a0 = new Date(a.getFullYear(), a.getMonth(), a.getDate()).getTime();
  const n0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((n0 - a0) / MS_PER_DAY);
}

// Highest day index that has data (for author/unlock mode ceiling).
export function maxDay() {
  const keys = GAME.dayIndexes();
  return keys.length ? Math.max(...keys) : 0;
}

// Lowest day index that has data.
export function minDay() {
  const keys = GAME.dayIndexes();
  return keys.length ? Math.min(...keys) : 0;
}

// Day indexes a visitor may open right now. Normal: data days with date<=today.
// Unlocked (author mode): every data day, including the future.
export function availableDays(now = new Date(), unlocked = false) {
  const ceil = unlocked ? maxDay() : todayIndex(now);
  return GAME.dayIndexes()
    .filter((n) => n <= ceil)
    .sort((a, b) => a - b);
}

// The day to show by default (latest available, never a future spoiler).
export function currentDay(now = new Date(), unlocked = false) {
  const avail = availableDays(now, unlocked);
  return avail.length ? avail[avail.length - 1] : minDay();
}

// Resolve a requested ?day=N into a playable index. Falls back to currentDay if
// the request is missing, malformed, or not yet available.
export function resolveDay(requested, now = new Date(), unlocked = false) {
  const n = Number(requested);
  if (requested === null || requested === undefined || requested === '' || Number.isNaN(n)) {
    return currentDay(now, unlocked);
  }
  const avail = new Set(availableDays(now, unlocked));
  return avail.has(n) ? n : currentDay(now, unlocked);
}

// Localized date label for a day index.
export function fmtDate(idx, locale = undefined) {
  return dateForDay(idx).toLocaleDateString(locale, {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });
}

// Milliseconds from `now` until the player's next LOCAL midnight (for the
// "next game in HH:MM" countdown on the end screen).
export function msUntilLocalMidnight(now = new Date()) {
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return next.getTime() - now.getTime();
}
