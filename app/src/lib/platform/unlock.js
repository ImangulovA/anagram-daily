// ---------------------------------------------------------------------------
// "Author mode" gate: unlock playing FUTURE days early. PLATFORM code.
//
// OBFUSCATION, not security. Future days already ship in the static bundle, so a
// determined visitor can read them from source regardless. The gate keeps casual
// players off unreleased days and lets you share early access via a link.
// Disabled entirely when UNLOCK_PASSWORD is '' in config.js.
// ---------------------------------------------------------------------------
import { UNLOCK_PASSWORD } from '../config.js';
import { GAME } from '../game/index.js';

const KEY = () => `${GAME.id}_unlocked`;

export function unlockEnabled() {
  return !!UNLOCK_PASSWORD;
}

export function isUnlocked() {
  if (!UNLOCK_PASSWORD) return false;
  if (typeof localStorage === 'undefined') return false; // SSR / prerender
  return localStorage.getItem(KEY()) === '1';
}

export function setUnlocked(on) {
  if (typeof localStorage === 'undefined') return;
  if (on) localStorage.setItem(KEY(), '1');
  else localStorage.removeItem(KEY());
}

// Read `?unlock=<password>` from the URL. If it matches, persist the flag and
// strip the param (keeping any other params, e.g. ?day=N). Returns the resulting
// unlocked state. Safe to call when already unlocked.
export function applyUnlockFromUrl() {
  if (!UNLOCK_PASSWORD) return false;
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(location.search);
  const supplied = params.get('unlock');
  if (supplied !== null) {
    if (supplied === UNLOCK_PASSWORD) setUnlocked(true);
    params.delete('unlock');
    const qs = params.toString();
    const clean = location.pathname + (qs ? '?' + qs : '') + location.hash;
    history.replaceState(null, '', clean);
  }
  return isUnlocked();
}
