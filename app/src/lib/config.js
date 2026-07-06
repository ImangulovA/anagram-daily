// ---------------------------------------------------------------------------
// Per-fork configuration for Anagram Daily.
// ---------------------------------------------------------------------------

// Global-stats Worker (Cloudflare). Same worker the original static site used,
// so historical aggregates carry over. Set to '' to run LOCAL-ONLY (every
// network call no-ops and nothing breaks).
export const STATS_API = 'https://anagram-stats.ru-catfishing.workers.dev';

// Password that unlocks playing FUTURE (not-yet-released) days early via
// `?unlock=<this>&day=N`. OBFUSCATION, not security — future days ship in the
// bundle regardless. Set to '' to disable the author-mode gate entirely.
export const UNLOCK_PASSWORD = 'flagship';
