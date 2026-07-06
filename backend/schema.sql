-- Global-stats schema for Anagram Daily. Scores are stored as tenths
-- (score * 10, an integer 0..200) to keep the 0.5-point precision exact.
-- The `game` column namespaces rows (matches the daily_github_game pattern).

-- Idempotency log: one row per (game, client, day, kind). Dedupes retries /
-- backfills so aggregates never inflate.
CREATE TABLE IF NOT EXISTS events (
  game      TEXT NOT NULL,
  client_id TEXT NOT NULL,
  day       INTEGER NOT NULL,
  kind      TEXT NOT NULL,        -- 'start' | 'finish'
  ts        INTEGER NOT NULL,     -- epoch ms (client-supplied; informational)
  PRIMARY KEY (game, client_id, day, kind)
);

-- Rolled-up counters per (game, day).
CREATE TABLE IF NOT EXISTS day_stats (
  game               TEXT NOT NULL,
  day                INTEGER NOT NULL,
  started            INTEGER NOT NULL DEFAULT 0,
  finished           INTEGER NOT NULL DEFAULT 0,
  total_score_tenths INTEGER NOT NULL DEFAULT 0,  -- sum of finish scores (tenths)
  scored_count       INTEGER NOT NULL DEFAULT 0,  -- # finishes counted
  PRIMARY KEY (game, day)
);

-- Individual finish scores: one row per (game, day, client). Powers the score
-- distribution used for the mode + histogram.
CREATE TABLE IF NOT EXISTS finish_scores (
  game         TEXT NOT NULL,
  day          INTEGER NOT NULL,
  client_id    TEXT NOT NULL,
  score_tenths INTEGER NOT NULL,   -- score * 10 (0..200)
  PRIMARY KEY (game, day, client_id)
);
CREATE INDEX IF NOT EXISTS idx_finish_scores_game_day ON finish_scores (game, day);
