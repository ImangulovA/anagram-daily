<script>
  // ===========================================================================
  // Anagram Daily — the puzzle UI. Renders the two clue cards, the shared letter
  // pool, and the final-answer entry, and drives the pure scoring engine.
  //
  // Platform contract:
  //   props in:  puzzle, dayIdx, saved (resume snapshot | null)
  //   callbacks: onstart(), onprogress(state), onfinish(result)
  // ===========================================================================
  import { onMount } from 'svelte';
  import { createEngine } from './scoring.js';

  let {
    puzzle,
    dayIdx,
    saved = null,
    reveal = false,
    onstart,
    onprogress,
    onfinish
  } = $props();

  const engine = createEngine(puzzle, saved);

  const wordLen = {
    a: (puzzle.a.word || '').length,
    b: (puzzle.b.word || '').length,
    c: (puzzle.c.word || '').length
  };

  // Per-cell reactive UI state.
  let typedA = $state(Array(wordLen.a).fill(''));
  let typedB = $state(Array(wordLen.b).fill(''));
  let typedC = $state(Array(wordLen.c).fill(''));
  let lockedA = $state(Array(wordLen.a).fill(false));
  let lockedB = $state(Array(wordLen.b).fill(false));
  let lockedC = $state(Array(wordLen.c).fill(false));
  let correctA = $state(false);
  let correctB = $state(false);

  let score = $state(engine.state().score);
  let finished = $state(engine.state().finished);
  let clueRevealed = $state(engine.state().clueRevealed);
  let fbA = $state('');
  let fbB = $state('');
  let fbC = $state('');

  let poolOrder = $state([]);
  let poolEl;
  let poolW = $state(0);
  let rootEl;
  let startedOnce = false;

  // Win animation: letters fly from the sources and weave into the answer.
  let flyers = $state([]);
  let flying = $state(false);

  const typedOf = (w) => (w === 'a' ? typedA : w === 'b' ? typedB : typedC);
  const lockedOf = (w) => (w === 'a' ? lockedA : w === 'b' ? lockedB : lockedC);

  // Seed any revealed letters from a resumed snapshot (or reveal everything in
  // read-only "view puzzle" mode on the end screen).
  onMount(() => {
    if (reveal) {
      fillAllRevealed();
    } else {
      seedSource('a');
      seedSource('b');
      const snap = engine.snapshot();
      const c = engine.answers.c;
      (snap.revealedFinal || []).forEach((on, i) => {
        if (on) {
          typedC[i] = c.charAt(i);
          lockedC[i] = true;
        }
      });
      // A finished snapshot that reached the play view (e.g. the win animation
      // was interrupted before the platform recorded the finish) — finalize now
      // so the end screen shows instead of a stuck solved board.
      if (engine.state().finished) {
        setTimeout(() => onfinish?.(engine.result()), 0);
      }
    }
    reconcilePool();

    // Keep the pool sized to its (narrow) column.
    if (poolEl) {
      poolW = poolEl.clientWidth;
      if (typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(() => {
          poolW = poolEl.clientWidth;
        });
        ro.observe(poolEl);
        return () => ro.disconnect();
      }
    }
  });

  // Fill every box with the answer, locked + read-only (end-screen preview).
  function fillAllRevealed() {
    ['a', 'b', 'c'].forEach((w) => {
      const word = engine.answers[w];
      const typed = typedOf(w);
      const locked = lockedOf(w);
      for (let i = 0; i < word.length; i++) {
        typed[i] = word.charAt(i);
        locked[i] = true;
      }
    });
    correctA = true;
    correctB = true;
    clueRevealed = true;
    finished = true;
  }

  function seedSource(w) {
    const snap = engine.snapshot();
    const word = engine.answers[w];
    const rl = (snap.revealedLetters && snap.revealedLetters[w]) || [];
    const full = snap.fullReveal && snap.fullReveal[w];
    const typed = typedOf(w);
    const locked = lockedOf(w);
    for (let i = 0; i < word.length; i++) {
      if (full || rl[i]) {
        typed[i] = word.charAt(i);
        locked[i] = true;
      }
    }
  }

  // --- platform sync -------------------------------------------------------
  function ensureStarted() {
    if (!startedOnce) {
      startedOnce = true;
      onstart?.();
    }
  }
  function refresh() {
    const s = engine.state();
    score = s.score;
    finished = s.finished;
    clueRevealed = s.clueRevealed;
  }
  function commit() {
    refresh();
    onprogress?.(engine.snapshot());
  }
  function finish() {
    refresh();
    onfinish?.(engine.result());
  }

  // --- letter pool ---------------------------------------------------------
  function reconcilePool() {
    const target = [];
    for (const ch of typedA) if (ch) target.push(ch);
    for (const ch of typedB) if (ch) target.push(ch);
    const need = {};
    target.forEach((c) => (need[c] = (need[c] || 0) + 1));
    const kept = [];
    const seen = {};
    for (const c of poolOrder) {
      if ((seen[c] || 0) < (need[c] || 0)) {
        kept.push(c);
        seen[c] = (seen[c] || 0) + 1;
      }
    }
    for (const c of Object.keys(need)) {
      const missing = need[c] - (seen[c] || 0);
      for (let k = 0; k < missing; k++) kept.push(c);
    }
    poolOrder = kept;
  }

  // Pure layout: pack the (circular) tiles onto CONCENTRIC ELLIPSE rings inside a
  // PORTRAIT pool (taller than wide, so more letters fit and the ring looks a bit
  // bigger). Tiles are spaced by equal ARC LENGTH per ring; circular tiles => no
  // overlap when center-spacing >= diameter, which the arc spacing + a safety
  // margin guarantee. ASPECT must match the CSS `.pool { aspect-ratio }`.
  const POOL_ASPECT = 1.25; // height / width  (CSS aspect-ratio: 4 / 5)
  const RING_SAFE = 1.14; // capacity safety margin (curvature at ellipse ends)
  let placements = $derived(computePlacements(poolOrder, poolW));
  function computePlacements(order, size) {
    const n = order.length;
    if (!n || !size) return [];
    const h = size * POOL_ASPECT;
    const gap = 6;
    let chosen = null;
    for (let ts = 48; ts >= 12; ts -= 2) {
      const rings = packEllipse(n, size, h, ts, gap, false);
      if (rings) {
        chosen = { ts, rings };
        break;
      }
    }
    if (!chosen) chosen = { ts: 12, rings: packEllipse(n, size, h, 12, gap, true) };
    const { ts, rings } = chosen;
    const cx = size / 2;
    const cy = h / 2;
    const out = [];
    let idx = 0;
    rings.forEach((ring, ri) => {
      const phase = (ri * 0.5) / Math.max(1, ring.count); // stagger rings a touch
      const pts = ellipsePoints(ring.Rx, ring.Ry, ring.count, phase, cx, cy);
      for (const p of pts) {
        if (idx >= n) break;
        out.push({
          ch: order[idx],
          i: idx,
          left: p.x - ts / 2,
          top: p.y - ts / 2,
          w: ts,
          font: Math.max(11, Math.round(ts * 0.52))
        });
        idx++;
      }
    });
    return out;
  }

  // Ramanujan ellipse-perimeter approximation.
  function ellipsePerim(a, b) {
    if (a <= 0 && b <= 0) return 0;
    return Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b)));
  }

  // Points spaced by EQUAL ARC LENGTH around an ellipse (uniform gaps even where
  // the curve is flatter). Numerically integrates the arc, then samples.
  function ellipsePoints(Rx, Ry, count, phase, cx, cy) {
    if ((Rx <= 0 && Ry <= 0) || count <= 0) return count > 0 ? [{ x: cx, y: cy }] : [];
    const N = 240;
    const cum = [0];
    let px = cx + Rx;
    let py = cy;
    for (let k = 1; k <= N; k++) {
      const a = (2 * Math.PI * k) / N;
      const x = cx + Rx * Math.cos(a);
      const y = cy + Ry * Math.sin(a);
      cum.push(cum[k - 1] + Math.hypot(x - px, y - py));
      px = x;
      py = y;
    }
    const total = cum[N] || 1;
    const pts = [];
    for (let j = 0; j < count; j++) {
      let target = (j / count + phase) * total;
      target = ((target % total) + total) % total;
      let k = 1;
      while (k < N && cum[k] < target) k++;
      const seg = cum[k] - cum[k - 1] || 1;
      const t = (target - cum[k - 1]) / seg;
      const a = (2 * Math.PI * (k - 1 + t)) / N;
      pts.push({ x: cx + Rx * Math.cos(a), y: cy + Ry * Math.sin(a) });
    }
    return pts;
  }

  // Distribute n circular tiles (diameter ts) across concentric ellipse rings in
  // a w×h box. Returns [{ Rx, Ry, count }] outer-first, or null if it can't fit
  // (unless `force`). Ring capacity = perimeter / (spacing × safety margin).
  function packEllipse(n, w, h, ts, gap, force) {
    const cell = ts + gap;
    const capCell = cell * RING_SAFE;
    const maxRx = w / 2 - ts / 2 - 2;
    const maxRy = h / 2 - ts / 2 - 2;
    if (n === 1) return [{ Rx: 0, Ry: 0, count: 1 }];
    const geom = [];
    let Rx = maxRx;
    let Ry = maxRy;
    while (Rx >= cell * 0.6 && Ry >= cell * 0.6) {
      geom.push({ Rx, Ry });
      Rx -= cell;
      Ry -= cell;
    }
    const inner = geom.length ? geom[geom.length - 1] : null;
    const useCenter = !inner || (inner.Rx >= cell && inner.Ry >= cell);
    const slots = geom.map((g) => ({
      ...g,
      cap: Math.max(1, Math.floor(ellipsePerim(g.Rx, g.Ry) / capCell))
    }));
    if (useCenter) slots.push({ Rx: 0, Ry: 0, cap: 1 });
    const total = slots.reduce((s, x) => s + x.cap, 0);
    if (total < n && !force) return null;
    const rings = [];
    let remaining = n;
    for (const slot of slots) {
      if (remaining <= 0) break;
      const take = Math.min(slot.cap, remaining);
      rings.push({ Rx: slot.Rx, Ry: slot.Ry, count: take });
      remaining -= take;
    }
    if (remaining > 0) {
      if (force) rings.push({ Rx: 0, Ry: 0, count: remaining });
      else return null;
    }
    return rings;
  }

  function shuffleArr(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  function doShuffle() {
    if (finished) return;
    ensureStarted();
    engine.shuffle();
    poolOrder = shuffleArr(poolOrder);
    commit();
  }
  function placeInFinal(ch) {
    if (finished) return;
    for (let i = 0; i < wordLen.c; i++) {
      if (!lockedC[i] && !typedC[i]) {
        typedC[i] = ch;
        focusBox('c', i + 1);
        return;
      }
    }
  }

  // --- input handling ------------------------------------------------------
  function boxes(w) {
    if (!rootEl) return [];
    return Array.from(rootEl.querySelectorAll(`.lbox[data-w="${w}"]`));
  }
  function allBoxes() {
    if (!rootEl) return [];
    return Array.from(rootEl.querySelectorAll('.lbox'));
  }
  function focusBox(w, i) {
    const list = boxes(w);
    for (let j = i; j < list.length; j++) {
      if (!list[j].readOnly) {
        list[j].focus();
        return;
      }
    }
  }
  function focusAcross(el, dir) {
    const all = allBoxes();
    const cur = all.indexOf(el);
    let j = cur + dir;
    while (j >= 0 && j < all.length) {
      if (!all[j].readOnly) {
        all[j].focus();
        all[j].select();
        return;
      }
      j += dir;
    }
  }

  function onInput(w, i, e) {
    const v = (e.target.value || '').toUpperCase().replace(/[^A-Z]/g, '');
    const ch = v.slice(-1);
    typedOf(w)[i] = ch;
    e.target.value = ch;
    ensureStarted();
    if (w === 'a' || w === 'b') reconcilePool();
    clearFb(w);
    if (ch) focusBox(w, i + 1);
  }
  function onKey(w, i, e) {
    if (e.key === 'Backspace') {
      const typed = typedOf(w);
      if (!typed[i]) {
        e.preventDefault();
        const list = boxes(w);
        for (let j = i - 1; j >= 0; j--) {
          if (!list[j].readOnly) {
            typed[j] = '';
            list[j].focus();
            break;
          }
        }
      } else {
        typed[i] = '';
      }
      if (w === 'a' || w === 'b') reconcilePool();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      focusAcross(e.target, e.shiftKey ? -1 : 1);
    } else if (e.key === 'Enter') {
      if (w === 'c') doSubmit();
      else doCheck(w);
    }
  }
  function clearFb(w) {
    if (w === 'a') fbA = '';
    else if (w === 'b') fbB = '';
    else fbC = '';
  }
  function collect(w) {
    return typedOf(w).join('').toUpperCase();
  }

  // --- scoring actions -----------------------------------------------------
  function doCheck(w) {
    if (finished) return;
    ensureStarted();
    const res = engine.checkSource(w, collect(w));
    if (res.correct) {
      const locked = lockedOf(w);
      for (let i = 0; i < locked.length; i++) locked[i] = true;
      if (w === 'a') {
        correctA = true;
        fbA = '✓ Correct';
      } else {
        correctB = true;
        fbB = '✓ Correct';
      }
    } else if (w === 'a') fbA = '✗ Not quite';
    else fbB = '✗ Not quite';
    commit();
  }
  function doRevealLetter(w) {
    if (finished) return;
    ensureStarted();
    const res = engine.revealSourceLetter(w);
    if (res && res.index >= 0) {
      typedOf(w)[res.index] = res.letter;
      lockedOf(w)[res.index] = true;
      reconcilePool();
    }
    commit();
  }
  function doRevealWord(w) {
    if (finished) return;
    ensureStarted();
    const res = engine.revealSourceWord(w);
    const word = res.word || engine.answers[w];
    const typed = typedOf(w);
    const locked = lockedOf(w);
    for (let i = 0; i < word.length; i++) {
      typed[i] = word.charAt(i);
      locked[i] = true;
    }
    reconcilePool();
    if (w === 'a') fbA = 'Revealed';
    else fbB = 'Revealed';
    commit();
  }
  function doRevealFinalLetter() {
    if (finished) return;
    ensureStarted();
    const res = engine.revealFinalLetter();
    if (res && res.index >= 0) {
      typedC[res.index] = res.letter;
      lockedC[res.index] = true;
    }
    commit();
  }
  function doRevealClue() {
    if (finished || clueRevealed) return;
    ensureStarted();
    engine.revealFinalClue();
    commit();
  }
  let shakeC = $state(false);
  function doSubmit() {
    if (finished) return;
    ensureStarted();
    if (collect('c').length < wordLen.c) {
      triggerShake();
      return;
    }
    const res = engine.guessFinal(collect('c'));
    if (res.correct) {
      for (let i = 0; i < wordLen.c; i++) lockedC[i] = true;
      fbC = '✓ Solved!';
      refresh(); // finished=true locally (disables buttons) — but stay mounted
      onprogress?.(engine.snapshot()); // persist the finished snapshot
      const anim = celebrate();
      const wait = anim ? 1300 + wordLen.c * 55 : 0;
      // Keep the component mounted until the letters land, THEN hand off to the
      // platform (which switches to the end screen and unmounts us).
      setTimeout(() => {
        flying = false;
        flyers = [];
        onfinish?.(engine.result());
      }, wait);
    } else {
      fbC = '✗ Wrong (-1)';
      triggerShake();
      commit();
    }
  }

  const prefersReduced = () =>
    typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Spawn flying letters: each answer letter starts at a source cell (A/B boxes,
  // else the pool tiles) and arcs — with a sideways sway + spin — into its final
  // box. Returns false if animation is skipped (reduced motion / no boxes).
  function celebrate() {
    if (prefersReduced() || !rootEl) return false;
    const cEls = boxes('c');
    if (!cEls.length) return false;
    const HALF = 17; // flyer is 34px; translate targets its top-left
    const pt = (r) => ({ x: r.left + r.width / 2 - HALF, y: r.top + r.height / 2 - HALF });
    const srcEls = [...boxes('a'), ...boxes('b')].filter((e) => e.value);
    const poolEls = Array.from(rootEl.querySelectorAll('.tile'));
    const src = srcEls.length ? srcEls : poolEls;
    const srcPts = src.map((e) => pt(e.getBoundingClientRect()));
    const answer = engine.answers.c;
    const list = [];
    for (let i = 0; i < cEls.length; i++) {
      const end = pt(cEls[i].getBoundingClientRect());
      const start = srcPts.length
        ? srcPts[i % srcPts.length]
        : { x: (typeof window !== 'undefined' ? window.innerWidth / 2 : 160) - HALF, y: -40 };
      const sway = Math.random() * 160 - 80;
      const peak = 50 + Math.random() * 90;
      list.push({
        ch: answer.charAt(i),
        key: i,
        x0: start.x,
        y0: start.y,
        x1: end.x,
        y1: end.y,
        mx: (start.x + end.x) / 2 + sway,
        my: (start.y + end.y) / 2 - peak,
        rot: (Math.random() * 720 - 360) | 0,
        delay: i * 55
      });
    }
    flyers = list;
    flying = true;
    return true;
  }
  function triggerShake() {
    shakeC = false;
    requestAnimationFrame(() => (shakeC = true));
    setTimeout(() => (shakeC = false), 450);
  }
  function doGiveUp() {
    if (finished) return;
    if (!confirm('Give up? Your score for today becomes 0.')) return;
    ensureStarted();
    engine.giveUp();
    finish();
  }

  const stars = (d) => {
    d = Math.max(1, Math.min(5, d || 1));
    return '★'.repeat(d) + '☆'.repeat(5 - d);
  };
</script>

<div class="anagram" bind:this={rootEl}>
  {#if !reveal}
    <div class="scorebar">
      <span class="score-pill">{score.toFixed(1)} / 20</span>
      <span class="diff">Difficulty {stars(puzzle.difficulty)}</span>
    </div>
  {/if}

  <div class="top-row">
    <!-- Clue 1 -->
    <section class="src-card">
      <h3>Clue 1</h3>
      <p class="clue">{puzzle.a.clue}</p>
      <div class="boxes">
        {#each typedA as ch, i}
          <input
            class="lbox"
            class:locked={lockedA[i]}
            class:correct={correctA}
            data-w="a"
            maxlength="1"
            autocomplete="off"
            autocapitalize="characters"
            inputmode="latin"
            aria-label={`Word A letter ${i + 1}`}
            value={ch}
            readonly={lockedA[i]}
            oninput={(e) => onInput('a', i, e)}
            onkeydown={(e) => onKey('a', i, e)}
            onfocus={(e) => e.target.select()}
          />
        {/each}
      </div>
      {#if !reveal}
        <div class="row-actions">
          <button class="btn primary" onclick={() => doCheck('a')} disabled={finished}
            >Check <span class="cost">-0.5</span></button
          >
          <button class="btn" onclick={() => doRevealLetter('a')} disabled={finished}
            >Reveal a letter <span class="cost">-1</span></button
          >
          <button class="btn ghost" onclick={() => doRevealWord('a')} disabled={finished}
            >Reveal word <span class="cost">-4</span></button
          >
          <span class="fb" class:ok={fbA.startsWith('✓')} class:no={fbA.startsWith('✗')}>{fbA}</span>
        </div>
      {/if}
    </section>

    <!-- Clue 2 -->
    <section class="src-card">
      <h3>Clue 2</h3>
      <p class="clue">{puzzle.b.clue}</p>
      <div class="boxes">
        {#each typedB as ch, i}
          <input
            class="lbox"
            class:locked={lockedB[i]}
            class:correct={correctB}
            data-w="b"
            maxlength="1"
            autocomplete="off"
            autocapitalize="characters"
            inputmode="latin"
            aria-label={`Word B letter ${i + 1}`}
            value={ch}
            readonly={lockedB[i]}
            oninput={(e) => onInput('b', i, e)}
            onkeydown={(e) => onKey('b', i, e)}
            onfocus={(e) => e.target.select()}
          />
        {/each}
      </div>
      {#if !reveal}
        <div class="row-actions">
          <button class="btn primary" onclick={() => doCheck('b')} disabled={finished}
            >Check <span class="cost">-0.5</span></button
          >
          <button class="btn" onclick={() => doRevealLetter('b')} disabled={finished}
            >Reveal a letter <span class="cost">-1</span></button
          >
          <button class="btn ghost" onclick={() => doRevealWord('b')} disabled={finished}
            >Reveal word <span class="cost">-4</span></button
          >
          <span class="fb" class:ok={fbB.startsWith('✓')} class:no={fbB.startsWith('✗')}>{fbB}</span>
        </div>
      {/if}
    </section>

    <!-- Letter pool -->
    <section class="pool-wrap">
      <h3>Letters</h3>
      <div class="pool" bind:this={poolEl}>
        {#if placements.length === 0}
          <span class="pool-empty">Solve the two clues — your letters appear here.</span>
        {:else}
          {#each placements as p (p.i)}
            <button
              class="tile"
              style="left:{p.left}px;top:{p.top}px;width:{p.w}px;height:{p.w}px;font-size:{p.font}px"
              onclick={() => placeInFinal(p.ch)}
              aria-label={`Letter ${p.ch}`}>{p.ch}</button
            >
          {/each}
        {/if}
      </div>
      {#if !reveal}
        <button class="btn" onclick={doShuffle} disabled={finished}
          >🔀 Shuffle <span class="cost">free</span></button
        >
      {/if}
    </section>
  </div>

  <!-- Final answer -->
  <section class="final-card">
    <h3>Final answer</h3>
    {#if clueRevealed}
      <p class="clue">{puzzle.c.clue}</p>
    {:else}
      <p class="clue hidden-clue">🔒 Clue hidden — reveal for -4</p>
    {/if}
    <div class="boxes final" class:shake={shakeC}>
      {#each typedC as ch, i}
        <input
          class="lbox"
          class:locked={lockedC[i]}
          data-w="c"
          maxlength="1"
          autocomplete="off"
          autocapitalize="characters"
          inputmode="latin"
          aria-label={`Final letter ${i + 1}`}
          value={ch}
          readonly={lockedC[i]}
          oninput={(e) => onInput('c', i, e)}
          onkeydown={(e) => onKey('c', i, e)}
          onfocus={(e) => e.target.select()}
        />
      {/each}
    </div>
    {#if !reveal}
      <div class="row-actions">
        <button class="btn primary" onclick={doSubmit} disabled={finished}
          >Submit <span class="cost">-1 if wrong</span></button
        >
        <button class="btn" onclick={doRevealClue} disabled={finished || clueRevealed}
          >Reveal clue <span class="cost">-4</span></button
        >
        <button class="btn" onclick={doRevealFinalLetter} disabled={finished}
          >Reveal a letter <span class="cost">-1.5</span></button
        >
        <button class="btn ghost" onclick={doGiveUp} disabled={finished}
          >Give up <span class="cost">→ 0</span></button
        >
        <span class="fb" class:ok={fbC.startsWith('✓')} class:no={fbC.startsWith('✗')}>{fbC}</span>
      </div>
    {/if}
  </section>

  {#if flying}
    <div class="celebrate-layer" aria-hidden="true">
      {#each flyers as f (f.key)}
        <span
          class="flyer"
          style="--x0:{f.x0}px;--y0:{f.y0}px;--x1:{f.x1}px;--y1:{f.y1}px;--mx:{f.mx}px;--my:{f.my}px;--rot:{f.rot}deg;animation-delay:{f.delay}ms"
          >{f.ch}</span
        >
      {/each}
    </div>
  {/if}
</div>

<style>
  .anagram {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .scorebar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }
  .score-pill {
    font-family: var(--mono);
    font-weight: 800;
    font-size: 16px;
    border: var(--border);
    border-radius: 8px;
    padding: 5px 12px;
    background: var(--accent);
    color: #111;
    box-shadow: var(--shadow);
  }
  .diff {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
  }
  h3 {
    margin: 0 0 4px;
    font-size: 12px;
    font-family: var(--mono);
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
  }
  .clue {
    font-size: 16px;
    font-weight: 600;
    margin: 2px 0 12px;
    min-height: 2.6em;
  }
  .hidden-clue {
    color: var(--muted);
    font-style: italic;
    font-weight: 500;
  }

  /* Bigger clue cards + a much narrower letter pool (2fr 2fr 1fr). */
  .top-row {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(0, 1.7fr) minmax(140px, 1.15fr);
    gap: 14px;
    align-items: start;
  }
  .src-card,
  .pool-wrap,
  .final-card {
    background: var(--surface-2);
    border: var(--border);
    border-radius: 12px;
    box-shadow: var(--shadow);
    padding: 14px;
  }
  .final-card {
    border-color: var(--accent);
  }
  .pool-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .pool-wrap h3 {
    align-self: flex-start;
  }
  @media (max-width: 760px) {
    .top-row {
      grid-template-columns: 1fr 1fr;
    }
    .pool-wrap {
      grid-column: 1 / -1;
    }
  }
  @media (max-width: 520px) {
    .top-row {
      grid-template-columns: 1fr;
    }
  }

  /* Letter boxes. Clue 1 & 2 (and the final word) stay on ONE row. */
  .boxes {
    display: flex;
    gap: 5px;
    margin-bottom: 12px;
  }
  .src-card .boxes,
  .boxes.final {
    flex-wrap: nowrap;
  }
  .lbox {
    width: 38px;
    height: 44px;
    border: var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--ink);
    font-family: var(--mono);
    font-weight: 800;
    font-size: 20px;
    text-align: center;
    text-transform: uppercase;
    padding: 0;
    box-shadow: 3px 3px 0 var(--ink);
  }
  .src-card .lbox,
  .boxes.final .lbox {
    flex: 1 1 0;
    min-width: 0;
    width: auto;
    max-width: 52px;
  }
  .lbox:focus {
    outline: none;
    box-shadow: 0 0 0 3px var(--accent);
  }
  .lbox.locked {
    background: var(--box-lock, #fff3c4);
  }
  .lbox.correct {
    background: var(--good);
    color: #08210f;
  }

  /* Narrow circular pool; tiles positioned + sized by JS. */
  /* Portrait pool: taller than wide (aspect-ratio 4/5 => height = width*1.25),
     so the letter ring is bigger and fits more. Must match POOL_ASPECT in JS. */
  .pool {
    position: relative;
    width: 100%;
    max-width: 210px;
    aspect-ratio: 4 / 5;
    margin: 6px auto 10px;
  }
  @media (max-width: 760px) {
    .pool {
      max-width: 240px;
    }
  }
  .pool-empty {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 84%;
    text-align: center;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    line-height: 1.4;
  }
  .tile {
    position: absolute;
    border: var(--border);
    border-radius: 50%;
    background: var(--accent);
    color: #111;
    font-family: var(--mono);
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 3px 3px 0 var(--ink);
    cursor: pointer;
    transition:
      left 0.18s ease,
      top 0.18s ease,
      transform 0.1s ease;
  }
  .tile:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }

  .row-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .btn {
    border: var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--ink);
    font-weight: 700;
    font-size: 13px;
    padding: 8px 12px;
    box-shadow: 3px 3px 0 var(--ink);
    cursor: pointer;
  }
  .btn:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
  .btn.primary {
    background: var(--accent);
    color: #111;
  }
  .btn.ghost {
    background: transparent;
  }
  .btn[disabled] {
    opacity: 0.45;
    cursor: not-allowed;
    box-shadow: none;
    transform: none;
  }
  .cost {
    font-family: var(--mono);
    font-size: 11px;
    opacity: 0.75;
    margin-left: 2px;
  }
  .fb {
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 700;
  }
  .fb.ok {
    color: var(--good);
  }
  .fb.no {
    color: var(--bad);
  }
  /* --- Win animation: letters flying into the answer --- */
  .celebrate-layer {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 9999;
  }
  .flyer {
    position: fixed;
    left: 0;
    top: 0;
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--mono);
    font-weight: 800;
    font-size: 18px;
    color: #111;
    background: var(--accent);
    border: var(--border);
    border-radius: 50%;
    box-shadow: 3px 3px 0 var(--ink);
    opacity: 0;
    transform: translate(var(--x0), var(--y0));
    animation: fly 1.15s cubic-bezier(0.5, -0.2, 0.2, 1) forwards;
    will-change: transform, opacity;
  }
  @keyframes fly {
    0% {
      opacity: 0;
      transform: translate(var(--x0), var(--y0)) scale(0.5) rotate(0deg);
    }
    14% {
      opacity: 1;
      transform: translate(var(--x0), var(--y0)) scale(1.25)
        rotate(calc(var(--rot) * 0.15));
    }
    55% {
      opacity: 1;
      transform: translate(var(--mx), var(--my)) scale(1.1) rotate(var(--rot));
    }
    100% {
      opacity: 1;
      transform: translate(var(--x1), var(--y1)) scale(1) rotate(0deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .flyer {
      animation: none;
      display: none;
    }
  }

  .shake {
    animation: shake 0.4s;
  }
  @keyframes shake {
    0%,
    100% {
      transform: translateX(0);
    }
    20% {
      transform: translateX(-8px);
    }
    40% {
      transform: translateX(8px);
    }
    60% {
      transform: translateX(-6px);
    }
    80% {
      transform: translateX(6px);
    }
  }
</style>
