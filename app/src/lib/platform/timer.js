// ---------------------------------------------------------------------------
// Active-play timer. PLATFORM code. Counts wall-clock time the player actually
// spends on the game: it PAUSES when the tab is hidden (visibilitychange) so an
// abandoned-but-open tab doesn't inflate "average time".
//
// Usage:
//   const t = makeTimer(savedElapsedMs);
//   t.start();                 // on first interaction
//   ...
//   const ms = t.stop();       // on finish — returns total active ms
//   t.elapsed();               // current total at any moment
//   t.destroy();               // remove the visibility listener on unmount
// ---------------------------------------------------------------------------

export function makeTimer(initialMs = 0) {
  let accumulated = initialMs; // ms banked from previous active spans
  let spanStart = null; // epoch ms when the current active span began
  let running = false;

  const now = () => (typeof performance !== 'undefined' ? performance.now() : 0);

  function bank() {
    if (spanStart !== null) {
      accumulated += now() - spanStart;
      spanStart = null;
    }
  }

  function resume() {
    if (running && spanStart === null) spanStart = now();
  }

  function onVisibility() {
    if (typeof document === 'undefined') return;
    if (document.hidden) bank();
    else resume();
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility);
  }

  return {
    start() {
      if (running) return;
      running = true;
      if (typeof document === 'undefined' || !document.hidden) spanStart = now();
    },
    stop() {
      bank();
      running = false;
      return Math.round(accumulated);
    },
    elapsed() {
      const live = spanStart !== null ? now() - spanStart : 0;
      return Math.round(accumulated + live);
    },
    isRunning() {
      return running;
    },
    destroy() {
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    }
  };
}

// Format ms as M:SS (or H:MM:SS for long games).
export function fmtTime(ms) {
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
