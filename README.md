# Anagram Daily

A daily word game. Two clues resolve to two source words (**A** and **B**);
their combined letters are an anagram of a third clued word (**C**, the answer).
Type A and B into crossword-style letter boxes, use the shuffle-able **letter
pool** to spot the anagram, then enter the final answer. Hints cost points.

Built as a fork of [`daily_github_game`](https://github.com/ImangulovA/daily_github_game),
so it shares the header/footer, theme, archive, stats, and global-stats plumbing
with the other daily games (Train Tracks, Battleships).

Live: https://imangulova.github.io/anagram-daily/ · All games: https://imangulova.github.io/games/

## How to play

- Solve **Clue 1** and **Clue 2** into words A and B. Hit **Check** on a card to
  test what you typed (costs points).
- Stuck? **Reveal a letter** or **Reveal word** on a source card (costs points).
- The **letter pool** shows every letter of A + B. **Shuffle** is free. Tap tiles
  into the final-answer boxes to build word C.
- **Submit** the final answer. Wrong guesses shake and deduct. **Reveal a
  letter** / **Reveal clue** help on C; **Give up** ends the day at 0.
- Each day starts at **20.0** points, floored at 0. Your score, the three words
  with clues, global stats + a histogram, a **Share** button, and a countdown
  appear on the end screen.
- Use **Archive** / **Stats** in the header to replay past days and see totals.

## Repo layout

| Path | Role |
|---|---|
| `app/` | SvelteKit app (the fork). `src/lib/game/` holds the anagram-specific code; `src/lib/platform/` is shared platform code. |
| `app/src/lib/game/GameComponent.svelte` | The puzzle UI (clue cards, letter pool, final answer). |
| `app/src/lib/game/scoring.js` | Pure scoring engine (no storage; the platform persists). |
| `app/src/lib/game/data/days.js` | AUTO-GENERATED puzzle data (`dayIndexes()`/`loadDay()`). |
| `app/src/lib/game/index.js` | `GAME` config (id, anchor, scoreOf, shareLine). |
| `scripts/` | Puzzle generator (`gen_puzzles.py`) + verifier (`verify_puzzles.py`). |
| `data/` | Generator inputs/outputs (`words_defs.json`, `puzzles.json`). |
| `backend/` | Cloudflare Worker + D1 for global stats (`anagram-stats`). |

## Identifiers (important)

- **Storage key**: `anagram_day<N>` (`GAME.id = 'anagram'`) — matches the games
  hub and existing player progress.
- **Backend stats key**: `anagram-daily` (`GAME.statsId`, decoupled in
  `platform/api.js`) — matches the live `anagram-stats` worker's data.
- **Day 0** = local midnight **2026-07-05** (`GAME.anchorDate = [2026, 6, 5]`),
  `Math.round`-based day math (DST-safe), matching the hub.

## Develop / build

Node is not system-wide here: `export PATH="$HOME/.local/node/bin:$PATH"`.

```bash
cd app
npm install          # CI does this; locally node_modules is reused from the fork
npm run dev          # local dev server
BASE_PATH=/anagram-daily npm run build   # production build -> app/build
```

## Regenerate puzzles

```bash
.venv/bin/python scripts/gen_puzzles.py     # writes data/puzzles.* AND app/src/lib/game/data/days.js
.venv/bin/python scripts/verify_puzzles.py  # mandatory gate (invariants + no cognate answers)
```

## Deploy

GitHub Actions (`.github/workflows/deploy.yml`) builds `app/` and publishes
`app/build` to GitHub Pages on every push to `main`. Pages source must be
**GitHub Actions** (the workflow's `configure-pages` step enables it).

## Style

Neobrutalism (shared with the sibling games): warm-light default + dark toggle,
accent `#fdc800`, bold borders, hard offset shadows, Inter + JetBrains Mono.
