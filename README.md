# Anagram Daily

A daily word game. Two clues resolve to two source words (**A** and **B**);
their combined letters are an anagram of a third clued word (**C**, the answer).
Type A and B into crossword-style letter boxes, use the shuffle-able **letter
pool** to spot the anagram, then enter the final answer. Hints cost points.

Live (via the games hub): https://imangulova.github.io/games/

## How to play

- Solve **Clue 1** and **Clue 2** into words A and B. Hit **Check** on a card to
  test what you typed (costs points).
- Stuck? **Reveal a letter** or **Reveal word** on a source card (costs points).
- The **letter pool** shows every letter of A + B. **Shuffle** is free. Tap or
  drag tiles into the final-answer boxes to build word C.
- **Submit** the final answer. Wrong guesses shake and deduct. **Reveal a
  letter** helps on C; **Give up** ends the day at 0.
- Each day starts at **20.00** points, floored at 0. Your score, the three words
  with clues, a **Share** button, and a countdown to the next puzzle appear on
  the end screen.
- The **calendar** (top-right) lets you replay past days. Future days are locked.

## Run locally

No build step. It is a static site and works from `file://`, but a tiny HTTP
server avoids browser quirks:

```bash
cd anagram-daily
python3 -m http.server 8000
# open http://localhost:8000/
```

## Architecture

Four independent pieces (see `CONTRACT.md` for the shared schema):

| File | Owner | Role |
|---|---|---|
| `index.html` | Agent 4 | Self-contained UI (CSS + game JS inline). Loads the two scripts below. |
| `scoring.js` | Agent 3 | `window.AnagramScoring` — all scoring/stats/share logic. |
| `data/puzzles.js` | Agent 2 | `window.PUZZLES` — array of daily puzzles. |
| `data/words_defs.json` | Agent 1 | Dictionary of word → definition + frequency. |

`index.html` ships an inline **fallback** (one/two sample puzzles + a minimal
`AnagramScoring` shim) used *only* if the real modules are missing, so the UI
renders during parallel development. When the real files are present they take
precedence (they load first; the fallback checks `if(!window.X)`).

### Scoring: every UI action maps to an `AnagramScoring` call

The UI never computes costs. It calls a method and re-renders `game.state()`:

| UI action | Call | Cost (owned by scoring.js) |
|---|---|---|
| Shuffle pool | `game.shuffle()` | Free (UI owns tile order) |
| Check source A/B | `game.checkSource(which, typed)` | −0.5 |
| Reveal a source letter | `game.revealSourceLetter(which)` | −1 |
| Reveal a whole source word | `game.revealSourceWord(which)` | −4 (capped) |
| Reveal a final letter | `game.revealFinalLetter()` | −1.5 |
| Submit final answer | `game.guessFinal(typed)` | −1 if wrong |
| Give up | `game.giveUp()` | → 0 |
| Share | `game.shareText()` | — |

### Day index

Day 0 = local midnight **2026-07-05**.
`dayIndex = floor((localMidnightToday − anchor) / 86400000)` using local date
parts (DST-safe), matching the games hub and the other daily games.

## Style

Neobrutalism, warm-light default with a dark toggle (stored under the shared
`games_theme` localStorage key). Accent `#fdc800`, bold borders, hard offset
shadows. Inter + JetBrains Mono with **system fallbacks only** — no external
font/CDN requests, so it works fully offline. English UI, responsive, keyboard-
and touch-friendly.
