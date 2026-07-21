// api/azs-votes.js — общий краудсорс наличия топлива для слоя АЗС.
// GET  /api/azs-votes?ids=osm-1,osm-2  → агрегат отметок по станциям.
// POST /api/azs-votes  { station_id, status, cid }  → записать отметку.
// Хранилище: Upstash Redis через REST (env KV_REST_API_URL / KV_REST_API_TOKEN,
// подключены к проекту через Vercel Marketplace). Без зависимостей — как radar-state.js.
// ТЗ: docs/agents/tz-fuel-availability-2026-07.md (фаза 2). Приватность: IP не логируем.

var STATUSES = ["yes", "no", "queue", "limit"];
var WINDOW_MS = 6 * 60 * 60 * 1000;   // свежее окно для агрегата
var TTL_SEC = 24 * 60 * 60;           // авто-очистка ключа станции
var RL_SEC = 30;                      // 1 отметка с cid на станцию в 30 сек
var MAX_IDS = 60;                     // потолок станций на один GET

// ─── чистая логика агрегата (тестируется ниже без сети) ──────────────────────
// entries: { cid: '{"s":"queue","t":1699999999999}' } (как HGETALL из Redis)
function aggregate(entries, now) {
  var breakdown = { yes: 0, no: 0, queue: 0, limit: 0 };
  var count = 0, last = 0;
  Object.keys(entries || {}).forEach(function (cid) {
    var v; try { v = JSON.parse(entries[cid]); } catch (_) { return; }
    if (!v || STATUSES.indexOf(v.s) < 0 || typeof v.t !== "number") return;
    if (now - v.t > WINDOW_MS) return;            // протухло — не считаем
    breakdown[v.s]++; count++;
    if (v.t > last) last = v.t;
  });
  var top = null, best = 0;
  STATUSES.forEach(function (s) { if (breakdown[s] > best) { best = breakdown[s]; top = s; } });
  return { count: count, breakdown: breakdown, top_status: top, last_observed_at: last || null };
}

function validId(id) { return typeof id === "string" && /^[a-z0-9:_-]{1,48}$/i.test(id); }
function validCid(c) { return typeof c === "string" && c.length >= 3 && c.length <= 64; }

// ─── Upstash REST pipeline ───────────────────────────────────────────────────
async function upstash(commands) {
  var url = process.env.KV_REST_API_URL, token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) throw new Error("no-store");
  var r = await fetch(url.replace(/\/$/, "") + "/pipeline", {
    method: "POST",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: JSON.stringify(commands)
  });
  if (!r.ok) throw new Error("upstash " + r.status);
  return r.json(); // [{result:...}, ...]
}

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") { res.status(204).end(); return; }

  try {
    if (req.method === "GET") {
      var raw = (req.query && req.query.ids) || "";
      var ids = String(raw).split(",").map(function (s) { return s.trim(); })
        .filter(validId).slice(0, MAX_IDS);
      if (!ids.length) { res.status(200).json({}); return; }
      var out = await upstash(ids.map(function (id) { return ["HGETALL", "av:" + id]; }));
      var now = Date.now(), result = {};
      ids.forEach(function (id, i) {
        result[id] = aggregate(hgetallToObj(out[i] && out[i].result), now);
      });
      res.status(200).json(result);
      return;
    }

    if (req.method === "POST") {
      var body = req.body;
      if (typeof body === "string") { try { body = JSON.parse(body); } catch (_) { body = {}; } }
      body = body || {};
      var id = body.station_id, status = body.status, cid = body.cid;
      if (!validId(id) || STATUSES.indexOf(status) < 0 || !validCid(cid)) {
        res.status(400).json({ error: "bad-input" }); return;
      }
      // анти-спам: 1 отметка с cid на станцию в RL_SEC (не логируем IP)
      var rl = await upstash([["SET", "rl:" + cid + ":" + id, "1", "NX", "EX", String(RL_SEC)]]);
      if (!(rl[0] && rl[0].result === "OK")) { res.status(429).json({ error: "too-soon" }); return; }
      var val = JSON.stringify({ s: status, t: Date.now() });
      await upstash([["HSET", "av:" + id, cid, val], ["EXPIRE", "av:" + id, String(TTL_SEC)]]);
      res.status(200).json({ ok: true });
      return;
    }

    res.status(405).json({ error: "method-not-allowed" });
  } catch (e) {
    // рубильник на клиенте: при ошибке виджет остаётся device-local
    res.status(503).json({ error: String(e && e.message || e) });
  }
};

// HGETALL по REST возвращает плоский массив [field,value,field,value]; приводим к объекту.
function hgetallToObj(arr) {
  var o = {};
  if (Array.isArray(arr)) for (var i = 0; i + 1 < arr.length; i += 2) o[arr[i]] = arr[i + 1];
  else if (arr && typeof arr === "object") return arr; // на случай объектного формата
  return o;
}

module.exports.aggregate = aggregate;
module.exports.hgetallToObj = hgetallToObj;

// ─── self-check: node api/azs-votes.js ───────────────────────────────────────
if (require.main === module) {
  var assert = require("assert");
  var now = 1_000_000_000_000;
  var fresh = { a: JSON.stringify({ s: "queue", t: now - 1000 }),
                b: JSON.stringify({ s: "queue", t: now - 2000 }),
                c: JSON.stringify({ s: "yes",   t: now - 3000 }),
                d: JSON.stringify({ s: "no",    t: now - (WINDOW_MS + 5000) }) }; // протухшая
  var agg = aggregate(fresh, now);
  assert.strictEqual(agg.count, 3, "считаем только свежие (протухшая d выпадает)");
  assert.strictEqual(agg.breakdown.queue, 2);
  assert.strictEqual(agg.breakdown.yes, 1);
  assert.strictEqual(agg.breakdown.no, 0, "протухшее no не в счёте");
  assert.strictEqual(agg.top_status, "queue", "преобладает queue");
  assert.strictEqual(agg.last_observed_at, now - 1000);
  assert.deepStrictEqual(aggregate({}, now), { count: 0, breakdown: { yes: 0, no: 0, queue: 0, limit: 0 }, top_status: null, last_observed_at: null });
  assert.deepStrictEqual(hgetallToObj(["x", "1", "y", "2"]), { x: "1", y: "2" });
  assert.strictEqual(validId("osm-40889936"), true);
  assert.strictEqual(validId("a b"), false);
  assert.strictEqual(validCid("cid-12345"), true);
  assert.strictEqual(validCid("xx"), false);
  console.log("[azs-votes] self-test OK");
}
