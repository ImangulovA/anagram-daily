<script>
  // Archive as a month calendar. Uses GAME.dayIndexes for the full data range.
  // Past/today are always playable; FUTURE days that have data are playable in
  // author mode (unlock) — see platform/unlock.js.
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { dateForDay, todayIndex } from '$lib/platform/days.js';
  import { GAME } from '$lib/game/index.js';
  import { loadDay } from '$lib/platform/storage.js';
  import { isUnlocked } from '$lib/platform/unlock.js';
  import { fmtTime } from '$lib/platform/timer.js';

  const WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  let months = $state([]);
  let locked = $state(false); // are there future days gated behind unlock?

  onMount(() => {
    const today = todayIndex();
    const unlocked = isUnlocked();
    const idxs = GAME.dayIndexes()
      .slice()
      .sort((a, b) => a - b);
    if (!idxs.length) return;

    const byDate = new Map();
    let anyLocked = false;
    for (const idx of idxs) {
      const d = dateForDay(idx);
      const r = loadDay(idx);
      const future = idx > today;
      const playable = !future || unlocked;
      if (future && !unlocked) anyLocked = true;
      byDate.set(`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`, {
        idx,
        dom: d.getDate(),
        status: r.finished ? 'done' : r.started ? 'progress' : 'new',
        ms: r.elapsedMs,
        future,
        isToday: idx === today,
        playable
      });
    }
    locked = anyLocked;

    const first = dateForDay(idxs[0]);
    const last = dateForDay(idxs[idxs.length - 1]);
    const out = [];
    let y = first.getFullYear();
    let m = first.getMonth();
    while (y < last.getFullYear() || (y === last.getFullYear() && m <= last.getMonth())) {
      const firstOfMonth = new Date(y, m, 1);
      const offset = (firstOfMonth.getDay() + 6) % 7; // Monday-first
      const daysInMonth = new Date(y, m + 1, 0).getDate();
      const cells = [];
      for (let i = 0; i < offset; i++) cells.push(null);
      for (let dom = 1; dom <= daysInMonth; dom++) {
        cells.push(byDate.get(`${y}-${m}-${dom}`) || { blank: true, dom });
      }
      while (cells.length % 7) cells.push(null);
      const weeks = [];
      for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
      out.push({
        label: firstOfMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }),
        weeks
      });
      m++;
      if (m > 11) {
        m = 0;
        y++;
      }
    }
    months = out;
  });
</script>

<h1>Archive</h1>

{#if months.length === 0}
  <p class="muted">No days available yet.</p>
{:else}
  {#if locked}
    <p class="hint">
      Future days unlock on their date. Author mode: open a link with
      <code>?unlock=…&amp;day=N</code> once and access is remembered.
    </p>
  {/if}

  {#each months as month}
    <section class="month">
      <h2>{month.label}</h2>
      <div class="cal">
        {#each WD as w}<div class="wd">{w}</div>{/each}
        {#each month.weeks as week}
          {#each week as cell}
            {#if cell === null}
              <div class="cell pad"></div>
            {:else if cell.blank}
              <div class="cell empty">{cell.dom}</div>
            {:else if cell.playable}
              <a
                class="cell day status-{cell.status}"
                class:today={cell.isToday}
                class:future={cell.future}
                href="{base}/?day={cell.idx}"
                title={cell.status === 'done' ? `Solved · ${fmtTime(cell.ms)}` : 'Play'}
              >
                <span class="dom">{cell.dom}</span>
                <span class="mark">
                  {#if cell.status === 'done'}✓{:else if cell.status === 'progress'}…{/if}
                </span>
              </a>
            {:else}
              <div class="cell day locked" title="Unlocks on its day">
                <span class="dom">{cell.dom}</span>
                <span class="mark">🔒</span>
              </div>
            {/if}
          {/each}
        {/each}
      </div>
    </section>
  {/each}
{/if}

<style>
  h1 {
    font-size: 24px;
  }
  .muted {
    color: var(--muted);
  }
  .hint {
    color: var(--muted);
    font-size: 13px;
    margin: 8px 0 16px;
  }
  code {
    font-family: var(--mono);
    background: var(--surface-2);
    padding: 1px 4px;
    border-radius: 4px;
  }
  .month {
    margin: 18px 0;
  }
  h2 {
    font-size: 16px;
    text-transform: capitalize;
    margin: 0 0 8px;
  }
  .cal {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 6px;
  }
  .wd {
    text-align: center;
    font-size: 11px;
    color: var(--muted);
    font-weight: 700;
    padding-bottom: 2px;
  }
  .cell {
    aspect-ratio: 1 / 1;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 5px 6px;
    font-family: var(--mono);
  }
  .pad {
    background: transparent;
  }
  .empty {
    color: color-mix(in srgb, var(--muted) 45%, transparent);
    font-size: 12px;
  }
  .day {
    background: var(--surface);
    border: var(--border);
    box-shadow: var(--shadow);
    color: var(--ink);
    text-decoration: none;
  }
  a.day:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
  .dom {
    font-size: 13px;
    font-weight: 700;
  }
  .mark {
    align-self: flex-end;
    font-size: 13px;
    line-height: 1;
    min-height: 13px;
  }
  .status-done {
    background: color-mix(in srgb, var(--good) 22%, var(--surface));
  }
  .status-done .mark {
    color: var(--good);
  }
  .status-new .dom {
    color: var(--accent-2);
  }
  .today {
    outline: 3px solid var(--accent);
    outline-offset: 1px;
  }
  .future {
    border-style: dashed;
  }
  .locked {
    background: var(--surface);
    border: 2px dashed color-mix(in srgb, var(--muted) 55%, transparent);
    box-shadow: none;
    color: var(--muted);
    opacity: 0.7;
  }
  .locked .mark {
    font-size: 11px;
  }
</style>
