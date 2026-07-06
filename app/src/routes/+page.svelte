<script>
  // ===========================================================================
  // GAME SHELL — PLATFORM code, customized end screen for Anagram Daily (score
  // based: shows the score, reveals the three words, and a gated histogram).
  // ===========================================================================
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';
  import { GAME } from '$lib/game/index.js';
  import { resolveDay, todayIndex, fmtDate, msUntilLocalMidnight } from '$lib/platform/days.js';
  import { loadDay as loadRecord, saveDay } from '$lib/platform/storage.js';
  import { makeTimer, fmtTime } from '$lib/platform/timer.js';
  import { submitStart, submitFinish, fetchAgg, statsEnabled } from '$lib/platform/api.js';
  import { applyUnlockFromUrl } from '$lib/platform/unlock.js';

  let dayIdx = $state(0);
  let puzzle = $state(null);
  let record = $state(null);
  let view = $state('loading'); // loading | intro | play | end | empty
  let isFuture = $state(false);
  let agg = $state(null);
  let untilMidnight = $state('');

  let timer = null;
  let tick = null;

  onMount(() => {
    const unlocked = applyUnlockFromUrl();
    const requested = new URLSearchParams(location.search).get('day');
    dayIdx = resolveDay(requested, new Date(), unlocked);
    puzzle = GAME.loadDay(dayIdx);
    if (!puzzle) {
      view = 'empty';
      return;
    }
    isFuture = dayIdx > todayIndex();
    record = loadRecord(dayIdx);
    timer = makeTimer(record.elapsedMs || 0);

    if (record.finished) {
      view = 'end';
      // Backfill possibly-missed beacons (idempotent server-side).
      submitStart(dayIdx);
      submitFinish(dayIdx, record.elapsedMs || 0, GAME.scoreOf ? GAME.scoreOf(record.result) : null);
      loadAgg();
    } else if (record.started) {
      submitStart(dayIdx);
      timer.start();
      view = 'play';
    } else {
      view = 'intro';
    }

    tick = setInterval(() => {
      untilMidnight = fmtTime(msUntilLocalMidnight());
    }, 1000);
    untilMidnight = fmtTime(msUntilLocalMidnight());
  });

  onDestroy(() => {
    timer?.destroy();
    if (tick) clearInterval(tick);
  });

  function persist() {
    saveDay(dayIdx, record);
  }
  function beginPlay() {
    view = 'play';
  }

  // --- callbacks handed to the game component -------------------------------
  function handleStart() {
    if (!record.started) {
      record.started = true;
      record.startedAt = Date.now();
      record.live = dayIdx === todayIndex();
      timer.start();
      persist();
      submitStart(dayIdx);
    }
  }
  function handleProgress(state) {
    record.state = state;
    record.elapsedMs = timer.elapsed();
    persist();
  }
  function handleFinish(result) {
    const ms = timer.stop();
    record.finished = true;
    record.finishedAt = Date.now();
    record.elapsedMs = ms;
    record.result = { ...result, ms };
    // `live` mirrors the other games' semantics for the hub badge.
    record.live = dayIdx === todayIndex();
    persist();
    submitFinish(dayIdx, ms, GAME.scoreOf ? GAME.scoreOf(record.result) : null);
    view = 'end';
    loadAgg();
    // Re-fetch shortly after so the just-posted finish is counted.
    setTimeout(loadAgg, 1600);
  }

  // --- end screen -----------------------------------------------------------
  async function loadAgg() {
    if (!statsEnabled()) return;
    agg = await fetchAgg([dayIdx]);
  }
  function dayAgg() {
    return agg?.agg?.[dayIdx] || null;
  }

  function trimNum(n) {
    if (typeof n !== 'number' || Number.isNaN(n)) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  }

  // Histogram: 0..20 in 0.5 steps (41 buckets). Only rendered with 10+ finishers.
  function histBars(a) {
    const counts = {};
    let maxN = 1;
    (a.hist || []).forEach((h) => {
      const k = Math.round(h.score * 2);
      counts[k] = (counts[k] || 0) + h.n;
      if (counts[k] > maxN) maxN = counts[k];
    });
    const mine = record?.result?.score;
    const mineKey = typeof mine === 'number' ? Math.round(mine * 2) : -1;
    const bars = [];
    for (let k = 0; k <= 40; k++) {
      const n = counts[k] || 0;
      bars.push({
        h: Math.round((n / maxN) * 60) + (n > 0 ? 4 : 0),
        you: k === mineKey,
        title: `${k / 2} pts · ${n} player${n === 1 ? '' : 's'}`
      });
    }
    return bars;
  }

  function shareText() {
    const url = `${location.origin}${base}/`;
    return GAME.shareLine(record.result, dayIdx, url);
  }

  // End-screen emoji recap: the same marks that go into the share block, decoded
  // into a small legend (the hint/check emojis aren't self-explanatory).
  const MARK_LEGEND = [
    ['⭐', 'Clean solve, no help'],
    ['💀', 'Gave up'],
    ['🟨', 'Source word revealed'],
    ['🔤', 'Source letter hint'],
    ['💡', 'Clue revealed'],
    ['🎯', 'Answer letter hint'],
    ['🔍', 'Check used'],
    ['❌', 'Wrong guess']
  ];
  function markLegend() {
    const marks = record?.result?.marks || '';
    const chars = [...marks];
    return MARK_LEGEND.map(([emoji, label]) => {
      const n = chars.filter((c) => c === emoji).length;
      return { emoji, label, n };
    }).filter((row) => row.n > 0);
  }
  // Which mark's tooltip is open (tap to toggle on mobile; also shows on hover).
  let activeMark = $state(-1);
  function toggleMark(e, i) {
    e.stopPropagation();
    activeMark = activeMark === i ? -1 : i;
  }
  let shared = $state('');
  let showPuzzle = $state(false); // end screen: preview the solved puzzle
  async function share() {
    const text = shareText();
    try {
      if (navigator.share) {
        await navigator.share({ text });
        shared = '';
        return;
      }
    } catch (e) {
      /* cancelled — fall through to clipboard */
    }
    try {
      await navigator.clipboard.writeText(text);
      shared = 'Copied!';
      setTimeout(() => (shared = ''), 2000);
    } catch (e) {
      shared = 'Copy failed';
    }
  }
</script>

<svelte:window onclick={() => (activeMark = -1)} />

{#if view === 'loading'}
  <p class="status">Loading…</p>
{:else if view === 'empty'}
  <div class="card">
    <h1>No puzzle for this day</h1>
    <p class="muted">This day isn't available yet. <a href="{base}/archive">Open the archive →</a></p>
  </div>
{:else}
  <div class="daybar">
    <span class="daychip" class:future={isFuture}>
      #{dayIdx} · {fmtDate(dayIdx)}{#if isFuture} · preview{/if}
    </span>
  </div>

  {#if view === 'intro'}
    <div class="card intro">
      <h1>{GAME.title}</h1>
      <p class="muted">{GAME.tagline}</p>
      {#if isFuture}<p class="future-note">🔓 Author mode: future day</p>{/if}
      <button class="primary" onclick={beginPlay}>Play</button>
    </div>
  {/if}

  {#if view === 'play'}
    <div class="card">
      <GAME.component
        {puzzle}
        {dayIdx}
        saved={record.state}
        onstart={handleStart}
        onprogress={handleProgress}
        onfinish={handleFinish}
      />
    </div>
  {/if}

  {#if view === 'end'}
    <div class="card end">
      <h1>{record.result?.won ? '🎉 Solved!' : 'Gave up'}</h1>
      <div class="bigscore">
        {trimNum(record.result?.score)} <span>/ {record.result?.max ?? 20}</span>
        {#if GAME.resultEmoji(record.result?.score)}
          <span class="celebrate">{GAME.resultEmoji(record.result.score)}</span>
        {/if}
      </div>

      {#if markLegend().length}
        <div class="marks">
          {#each markLegend() as row, i}
            <span
              class="mark"
              class:open={activeMark === i}
              role="button"
              tabindex="0"
              aria-label="{row.label}{row.n > 1 ? ` ×${row.n}` : ''}"
              onclick={(e) => toggleMark(e, i)}
              onkeydown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  toggleMark(e, i);
                }
              }}
            >
              <span class="mark-emoji">{row.emoji.repeat(row.n)}</span>
              <span class="tip">{row.label}{row.n > 1 ? ` ×${row.n}` : ''}</span>
            </span>
          {/each}
        </div>
      {/if}

      <div class="reveal">
        {#each [['1', puzzle.a], ['2', puzzle.b], ['★', puzzle.c]] as pair}
          <div class="reveal-row">
            <div class="rw">{pair[1].word}</div>
            <div class="rd">{pair[1].clue}</div>
          </div>
        {/each}
      </div>

      {#if dayAgg()}
        {@const a = dayAgg()}
        <div class="global">
          <h2>Today across all players</h2>
          <div class="grow">
            <div><span class="num">{a.started}</span><span class="lbl">started</span></div>
            <div><span class="num">{a.finished}</span><span class="lbl">finished</span></div>
            <div><span class="num">{trimNum(a.avgScore)}</span><span class="lbl">avg</span></div>
            <div><span class="num">{trimNum(a.modeScore)}</span><span class="lbl">most common</span></div>
          </div>

          {#if a.hist && a.hist.length && (a.finished || 0) >= 10}
            <div class="hist">
              {#each histBars(a) as bar}
                <div class="bar" class:you={bar.you} style="height:{bar.h}px" title={bar.title}></div>
              {/each}
            </div>
            <div class="hist-axis"><span>0</span><span>10</span><span>20</span></div>
            {#if typeof record?.result?.score === 'number'}
              <p class="hist-note">The gold bar is your score ({trimNum(record.result.score)}/20).</p>
            {/if}
          {:else if a.hist && a.hist.length}
            <p class="hist-note">Score distribution appears once 10+ players have finished today.</p>
          {/if}
        </div>
      {/if}

      <div class="actions">
        <button class="primary" onclick={share}>Share</button>
        <button class="ghost btnlike" onclick={() => (showPuzzle = !showPuzzle)}>
          {showPuzzle ? 'Hide puzzle' : 'View puzzle'}
        </button>
        <a class="ghost" href="{base}/stats">All stats →</a>
        <a class="ghost" href="{base}/archive">Archive →</a>
      </div>
      {#if shared}<p class="copied">{shared}</p>{/if}

      {#if showPuzzle}
        <div class="preview">
          <GAME.component
            {puzzle}
            {dayIdx}
            saved={record.state}
            reveal={true}
            onstart={() => {}}
            onprogress={() => {}}
            onfinish={() => {}}
          />
        </div>
      {/if}

      <p class="nextgame">Next puzzle in {untilMidnight}</p>
    </div>
  {/if}
{/if}

<style>
  .status {
    text-align: center;
    color: var(--muted);
    margin-top: 40px;
  }
  .daybar {
    display: flex;
    justify-content: center;
    margin-bottom: 12px;
  }
  .daychip {
    font-family: var(--mono);
    font-size: 13px;
    border: var(--border);
    background: var(--surface);
    box-shadow: var(--shadow);
    border-radius: 999px;
    padding: 4px 12px;
  }
  .daychip.future {
    border-style: dashed;
    color: var(--accent-2);
  }
  .card {
    background: var(--surface);
    border: var(--border);
    box-shadow: var(--shadow);
    border-radius: 14px;
    padding: 22px;
  }
  .intro,
  .end {
    text-align: center;
  }
  h1 {
    margin: 0 0 8px;
    font-size: 26px;
  }
  h2 {
    font-size: 16px;
    margin: 0 0 10px;
  }
  .muted {
    color: var(--muted);
  }
  .future-note {
    color: var(--accent-2);
    font-weight: 600;
  }
  .primary {
    border: var(--border);
    background: var(--accent);
    color: #111;
    box-shadow: var(--shadow);
    border-radius: 10px;
    padding: 10px 22px;
    font-weight: 800;
    font-size: 16px;
    cursor: pointer;
  }
  .primary:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
  .ghost {
    color: var(--ink);
    font-weight: 600;
    text-decoration: none;
    font-size: 15px;
  }
  .ghost:hover {
    text-decoration: underline;
  }
  .celebrate {
    font-size: 24px;
    margin-left: 6px;
    vertical-align: middle;
  }
  .bigscore {
    font-family: var(--mono);
    font-size: 44px;
    font-weight: 900;
    margin: 6px 0 14px;
  }
  .bigscore span {
    font-size: 22px;
    color: var(--muted);
  }
  .marks {
    font-size: 26px;
    margin: 0 0 12px;
    line-height: 1.2;
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 6px;
  }
  .mark {
    position: relative;
    cursor: help;
    border-radius: 8px;
    padding: 2px 4px;
  }
  .mark:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
  .mark-emoji {
    letter-spacing: 2px;
  }
  .tip {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%) translateY(4px);
    background: var(--ink);
    color: var(--surface);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0;
    white-space: nowrap;
    padding: 5px 9px;
    border-radius: 8px;
    opacity: 0;
    pointer-events: none;
    transition:
      opacity 0.12s ease,
      transform 0.12s ease;
    z-index: 5;
  }
  .tip::after {
    content: '';
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-top-color: var(--ink);
  }
  .mark:hover .tip,
  .mark.open .tip {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  .reveal {
    text-align: left;
    margin: 10px 0;
  }
  .reveal-row {
    border-top: 2px dashed var(--muted);
    padding: 10px 0;
  }
  .rw {
    font-family: var(--mono);
    font-weight: 900;
    font-size: 20px;
    letter-spacing: 2px;
  }
  .rd {
    color: var(--muted);
    font-size: 14px;
  }
  .global {
    border-top: var(--border);
    margin-top: 16px;
    padding-top: 14px;
  }
  .grow {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 18px;
    margin: 10px 0 14px;
  }
  .grow div {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .num {
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 700;
  }
  .lbl {
    color: var(--muted);
    font-size: 12px;
  }
  .hist {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 66px;
    justify-content: center;
  }
  .hist .bar {
    width: 10px;
    background: var(--muted);
    border: 2px solid var(--ink);
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    min-height: 3px;
    opacity: 0.55;
  }
  .hist .bar.you {
    background: var(--accent);
    opacity: 1;
  }
  .hist-axis {
    display: flex;
    justify-content: space-between;
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    margin-top: 4px;
    max-width: 460px;
    margin-inline: auto;
  }
  .hist-note {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
  }
  .actions {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 18px;
    margin-top: 18px;
  }
  .btnlike {
    background: none;
    border: none;
    cursor: pointer;
    font-family: inherit;
    padding: 0;
  }
  .preview {
    margin-top: 18px;
    padding-top: 16px;
    border-top: var(--border);
    text-align: left;
  }
  .copied {
    color: var(--good);
    font-size: 14px;
    margin: 8px 0 0;
  }
  .nextgame {
    color: var(--muted);
    font-family: var(--mono);
    font-size: 13px;
    margin: 16px 0 0;
  }
</style>
