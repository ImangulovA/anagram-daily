// ===========================================================================
// Anagram Daily — global-stats Worker. Records two lifecycle events per
// player-day (start, finish-with-score) and serves cross-player aggregates:
// started, finished, average score, mode score, and a score histogram.
// Stateless, CORS-guarded, idempotent. One D1 binding `DB`.
//
// Routes:
//   POST /start   { game, day, clientId }
//   POST /finish  { game, day, clientId, score }        score in 0..20 (0.5 steps)
//   GET  /agg?game=anagram-daily&days=1,2,3
//
// Bodies are parsed as JSON regardless of Content-Type (clients send text/plain
// so a POST stays a CORS "simple request" — no preflight).
// ===========================================================================

const DAY_MIN = -100;
const DAY_MAX = 100000;
const MAX_TENTHS = 200; // score 20.0

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin, env);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });

    try {
      if (request.method === 'POST' && url.pathname === '/start') {
        return await handleEvent(request, env, cors, 'start');
      }
      if (request.method === 'POST' && url.pathname === '/finish') {
        return await handleEvent(request, env, cors, 'finish');
      }
      if (request.method === 'GET' && url.pathname === '/agg') {
        return await handleAgg(url, env, cors);
      }
      if (url.pathname === '/') {
        return json({ ok: true, service: 'anagram-daily stats' }, 200, cors);
      }
      return json({ ok: false, error: 'not found' }, 404, cors);
    } catch (e) {
      return json({ ok: false, error: String(e) }, 500, cors);
    }
  }
};

function corsHeaders(origin, env) {
  const allowed = (env.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const allow = allowed.length === 0 || allowed.includes(origin) ? origin || '*' : allowed[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
  };
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json', ...cors }
  });
}

async function readBody(request) {
  const text = await request.text();
  try {
    return JSON.parse(text);
  } catch (e) {
    return {};
  }
}

function validDay(d) {
  return Number.isInteger(d) && d >= DAY_MIN && d <= DAY_MAX;
}

async function handleEvent(request, env, cors, kind) {
  const body = await readBody(request);
  const game = String(body.game || '').slice(0, 64);
  const day = Number(body.day);
  const clientId = String(body.clientId || '').slice(0, 64);
  if (!game || !clientId || !validDay(day)) {
    return json({ ok: false, error: 'bad request' }, 400, cors);
  }

  // Idempotent insert: if this (game, client, day, kind) already exists, the
  // INSERT is ignored and we skip the counter bump.
  const ins = await env.DB.prepare(
    'INSERT OR IGNORE INTO events (game, client_id, day, kind, ts) VALUES (?, ?, ?, ?, ?)'
  )
    .bind(game, clientId, day, kind, Date.now())
    .run();

  const isNew = ins.meta && ins.meta.changes > 0;
  if (!isNew) return json({ ok: true, deduped: true }, 200, cors);

  await env.DB.prepare('INSERT OR IGNORE INTO day_stats (game, day) VALUES (?, ?)')
    .bind(game, day)
    .run();

  if (kind === 'start') {
    await env.DB.prepare('UPDATE day_stats SET started = started + 1 WHERE game = ? AND day = ?')
      .bind(game, day)
      .run();
  } else {
    // Clamp score to 0..20 and store as tenths.
    let tenths = Math.round(Number(body.score) * 10);
    if (!Number.isFinite(tenths)) tenths = 0;
    tenths = Math.max(0, Math.min(MAX_TENTHS, tenths));

    await env.DB.prepare(
      `UPDATE day_stats
         SET finished = finished + 1,
             total_score_tenths = total_score_tenths + ?,
             scored_count = scored_count + 1
       WHERE game = ? AND day = ?`
    )
      .bind(tenths, game, day)
      .run();

    // Record this player's score (first finish counts) for the distribution.
    await env.DB.prepare(
      'INSERT OR IGNORE INTO finish_scores (game, day, client_id, score_tenths) VALUES (?, ?, ?, ?)'
    )
      .bind(game, day, clientId, tenths)
      .run();
  }

  return json({ ok: true }, 200, cors);
}

async function handleAgg(url, env, cors) {
  const game = String(url.searchParams.get('game') || '').slice(0, 64);
  if (!game) return json({ ok: false, error: 'missing game' }, 400, cors);

  const daysParam = (url.searchParams.get('days') || '').trim();
  const days = daysParam
    ? daysParam.split(',').map((x) => Number(x)).filter((n) => validDay(n))
    : [];

  let statRows;
  if (days.length) {
    const ph = days.map(() => '?').join(',');
    statRows = await env.DB.prepare(
      `SELECT day, started, finished, total_score_tenths, scored_count
         FROM day_stats WHERE game = ? AND day IN (${ph})`
    )
      .bind(game, ...days)
      .all();
  } else {
    statRows = await env.DB.prepare(
      `SELECT day, started, finished, total_score_tenths, scored_count
         FROM day_stats WHERE game = ?`
    )
      .bind(game)
      .all();
  }

  const agg = {};
  for (const r of statRows.results || []) {
    agg[r.day] = {
      started: r.started,
      finished: r.finished,
      finishRate: r.started ? r.finished / r.started : 0,
      avgScore: r.scored_count ? Math.round((r.total_score_tenths / r.scored_count)) / 10 : null,
      modeScore: null,
      count: r.scored_count,
      hist: []
    };
  }

  // Score distribution per day (for mode + histogram).
  let scoreRows;
  if (days.length) {
    const ph = days.map(() => '?').join(',');
    scoreRows = await env.DB.prepare(
      `SELECT day, score_tenths AS t, COUNT(*) AS n
         FROM finish_scores WHERE game = ? AND day IN (${ph})
         GROUP BY day, score_tenths ORDER BY day ASC, score_tenths ASC`
    )
      .bind(game, ...days)
      .all();
  } else {
    scoreRows = await env.DB.prepare(
      `SELECT day, score_tenths AS t, COUNT(*) AS n
         FROM finish_scores WHERE game = ?
         GROUP BY day, score_tenths ORDER BY day ASC, score_tenths ASC`
    )
      .bind(game)
      .all();
  }

  const modeBest = {}; // day -> {t, n}
  for (const r of scoreRows.results || []) {
    if (!agg[r.day]) {
      agg[r.day] = {
        started: 0, finished: 0, finishRate: 0, avgScore: null,
        modeScore: null, count: 0, hist: []
      };
    }
    agg[r.day].hist.push({ score: r.t / 10, n: r.n });
    const best = modeBest[r.day];
    if (!best || r.n > best.n) modeBest[r.day] = { t: r.t, n: r.n };
  }
  for (const day in modeBest) {
    if (agg[day]) agg[day].modeScore = modeBest[day].t / 10;
  }

  return json({ ok: true, agg }, 200, cors);
}
