<script>
  // Animated wordmark: the SAME 12 letters (4×A + N G R M D I L Y) hold for a
  // beat, then slowly slide into the next anagram of "Anagram Daily".
  // Monospace so every glyph is exactly 1ch wide → clean FLIP-style movement.
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';

  // fontSize: any CSS length. link=false renders a non-clickable hero (used
  // centered on the landing page instead of the header brand link).
  let { fontSize = '20px', link = true } = $props();

  const PHRASES = [
    'Anagram Daily',
    'Yada marginal',
    'Anagram Daily',
    'Damn Gray Alia',
    'I am lady angar'
  ];
  const HOLD = 1000; // ms static before each shuffle
  const MORPH = 1200; // ms letters take to travel to their new slot

  const COLS = Math.max(...PHRASES.map((p) => p.length)); // widest arrangement

  // Non-space letters of a phrase, each with its column index.
  function slotsOf(phrase) {
    const slots = [];
    [...phrase].forEach((ch, i) => {
      if (ch !== ' ') slots.push({ col: i, char: ch });
    });
    return slots;
  }

  let tokens = $state(slotsOf(PHRASES[0]).map((s, id) => ({ id, char: s.char, col: s.col })));

  // Reassign each persistent letter-token to a slot in the next phrase, matched
  // by letter (case-insensitive). Changing `col` triggers the CSS transition.
  function morphTo(phrase) {
    const pool = {};
    tokens.forEach((t, idx) => {
      const k = t.char.toUpperCase();
      (pool[k] ||= []).push(idx);
    });
    const next = tokens.map((t) => ({ ...t }));
    slotsOf(phrase).forEach((slot) => {
      const idx = pool[slot.char.toUpperCase()].shift();
      next[idx].col = slot.col;
      next[idx].char = slot.char;
    });
    tokens = next;
  }

  let timer;
  onMount(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let i = 0;
    const tick = () => {
      i = (i + 1) % PHRASES.length;
      morphTo(PHRASES[i]);
      timer = setTimeout(tick, HOLD + MORPH);
    };
    timer = setTimeout(tick, HOLD);
  });
  onDestroy(() => clearTimeout(timer));
</script>

{#snippet stage()}
  <span class="stage" aria-hidden="true" style="--cols:{COLS}; --morph:{MORPH}ms; font-size:{fontSize}">
    {#each tokens as t (t.id)}
      <span class="glyph" style="transform: translateX({t.col}ch); transition-delay:{(t.id % 6) * 45}ms"
        >{t.char}</span
      >
    {/each}
  </span>
{/snippet}

{#if link}
  <a class="brand" href="{base}/" aria-label={PHRASES[0]} data-sveltekit-reload>
    {@render stage()}
  </a>
{:else}
  <span class="brand hero" aria-label={PHRASES[0]}>
    {@render stage()}
  </span>
{/if}

<style>
  .brand {
    color: var(--ink);
    text-decoration: none;
    display: inline-block;
  }
  .stage {
    position: relative;
    display: inline-block;
    width: calc(var(--cols) * 1ch);
    height: 1.3em;
    font-family: var(--mono);
    font-weight: 800;
    line-height: 1.3em;
    white-space: nowrap;
  }
  .glyph {
    position: absolute;
    left: 0;
    top: 0;
    transition: transform var(--morph) cubic-bezier(0.6, 0.05, 0.25, 1);
    will-change: transform;
  }
</style>
