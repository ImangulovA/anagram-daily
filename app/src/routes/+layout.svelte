<script>
  // Global shell: design tokens (neobrutalism light/dark), theme toggle, header.
  // PLATFORM code — restyle freely per fork, but keep the CSS variables the game
  // component relies on (--accent, --surface-2, --border, --shadow, --mono, --muted).
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { page } from '$app/stores';
  import { GAME } from '$lib/game/index.js';
  import AnimatedLogo from '$lib/AnimatedLogo.svelte';

  let { children } = $props();
  let theme = $state('light');

  // Landing page (root route, no ?day) shows the animated wordmark centered in
  // the page, so the header brand is hidden there (via the `is-home` class on
  // <html>). The class is set pre-paint by an inline script in app.html; this
  // effect keeps it in sync across client-side navigations. Reading searchParams
  // here is safe because $effect only runs in the browser, never at prerender.
  $effect(() => {
    const home = $page.route.id === '/' && !$page.url.searchParams.has('day');
    document.documentElement.classList.toggle('is-home', home);
  });

  onMount(() => {
    const saved = localStorage.getItem('theme');
    theme = saved === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
  });

  function toggle() {
    theme = theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }
</script>

<svelte:head><title>{GAME.title}</title></svelte:head>

<header>
  <span class="logo-slot"><AnimatedLogo /></span>
  <nav>
    <a class="hub" href="https://imangulova.github.io/games/">◂ All games</a>
    <a href="{base}/archive">Archive</a>
    <a href="{base}/stats">Stats</a>
    <button class="themebtn" onclick={toggle} aria-label="Toggle theme">
      {theme === 'light' ? '🌙' : '☀️'}
    </button>
  </nav>
</header>

<main>
  {@render children()}
</main>

<footer>
  <span>Built from
    <a
      class="foot-brand"
      href="https://github.com/ImangulovA/daily_github_game"
      target="_blank"
      rel="noopener">daily_github_game</a>
  </span>
  <span class="foot-links">
    <a href="https://www.linkedin.com/in/imangulov" target="_blank" rel="noopener">LI</a>
    <span class="dot">·</span>
    <a href="https://imangulova.github.io/" target="_blank" rel="noopener">GH</a>
  </span>
</footer>

<style>
  :global(:root) {
    /* Neobrutalism — LIGHT (default; no dark flash before hydration) */
    --bg: #fdf6e3;
    --surface: #ffffff;
    --surface-2: #fff;
    --ink: #111111;
    --muted: #6b6b6b;
    --accent: #fdc800;
    --accent-2: #a855f7;
    --good: #02b070;
    --bad: #e0404a;
    --border: 2px solid #111111;
    --shadow: 5px 5px 0 #111111;
    --mono: 'JetBrains Mono', ui-monospace, monospace;
    --sans: 'Inter', system-ui, sans-serif;
  }
  :global([data-theme='dark']) {
    --bg: #0a0e1a;
    --surface: #151d30;
    --surface-2: #1d2740;
    --ink: #f3f4f6;
    --muted: #9aa3b2;
    --accent: #fdc800;
    --accent-2: #c084fc;
    --good: #02e2ac;
    --bad: #f87171;
    --border: 2px solid #f3f4f6;
    --shadow: 5px 5px 0 rgba(243, 244, 246, 0.85);
  }
  :global(html) {
    background: var(--bg);
  }
  :global(body) {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--sans);
    -webkit-font-smoothing: antialiased;
  }
  :global(*) {
    box-sizing: border-box;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    max-width: 720px;
    margin: 0 auto;
    padding: 18px 16px 0;
  }
  .logo-slot {
    display: inline-flex;
  }
  :global(html.is-home) .logo-slot {
    display: none;
  }
  nav {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-left: auto;
  }
  nav a {
    color: var(--ink);
    text-decoration: none;
    font-weight: 600;
    font-size: 15px;
  }
  nav a:hover {
    text-decoration: underline;
  }
  nav a.hub {
    color: var(--muted);
    font-weight: 700;
  }
  nav a.hub:hover {
    color: var(--ink);
  }
  .themebtn {
    border: var(--border);
    background: var(--surface);
    box-shadow: var(--shadow);
    border-radius: 8px;
    padding: 4px 8px;
    cursor: pointer;
    font-size: 15px;
  }
  .themebtn:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
  main {
    max-width: 720px;
    margin: 0 auto;
    padding: 16px;
  }
  footer {
    max-width: 720px;
    margin: 24px auto;
    padding: 0 16px;
    color: var(--muted);
    font-size: 13px;
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 6px 12px;
  }
  footer a {
    color: var(--muted);
    text-decoration: underline;
    font-weight: 600;
  }
  footer a:hover {
    color: var(--ink);
  }
  .foot-links {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .foot-links .dot {
    opacity: 0.6;
  }
</style>
