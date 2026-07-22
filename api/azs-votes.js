// api/azs-votes.js — общий краудсорс наличия топлива для слоя АЗС.
// GET  /api/azs-votes?ids=osm-1,osm-2  → агрегат отметок по станциям.
// GET  /api/azs-votes?active=1         → id станций со свежими отметками (для перекраски).
// GET  /api/azs-votes?feed=1           → лента последних отметок {id,status,t} (правая карточка).
// GET  /api/azs-votes?stats=1          → health+бюджет: активные станции + оценка команд/сутки.
// POST /api/azs-votes  { station_id, status, cid }  → записать отметку.
// Хранилище: Upstash Redis через REST (env KV_REST_API_URL / KV_REST_API_TOKEN,
// подключены к проекту через Vercel Marketplace). Без зависимостей — как radar-state.js.
// Анти-абьюз (#2): 1/cid/станцию/30с + лимит по IP (соль-хэш, IP не храним) + same-origin гейт.
// Мониторинг (#5): выборочный счётчик команд + Telegram-алерт при пороге бюджета Upstash.
// Опц. env: AZS_IP_SALT, AZS_CMD_ALERT_AT, AZS_ALLOWED_ORIGIN, AZS_ALERT_BOT_TOKEN, AZS_ALERT_CHAT_ID.
// ТЗ: docs/agents/tz-fuel-availability-2026-07.md (фаза 2). Приватность: IP не логируем.

var STATUSES = ["yes", "no", "queue", "limit"];
var WINDOW_MS = 6 * 60 * 60 * 1000;   // свежее окно для агрегата
var TTL_SEC = 24 * 60 * 60;           // авто-очистка ключа станции
var RL_SEC = 30;                      // 1 отметка с cid на станцию в 30 сек
var MAX_IDS = 60;                     // потолок станций на один GET
var FEED_MAX = 50;                    // сколько последних отметок держим в ленте активности

// #2 анти-абьюз: помимо 1/cid/станцию/30с — лимит по IP. IP НЕ храним: только соль-хэш
// с TTL (ephemeral rate-limit-токен, не привязан к личности — приватность ТЗ §4 цела).
var crypto = require("crypto");
var IP_LIMIT = 40;                    // отметок с одного IP за окно
var IP_WINDOW_SEC = 60 * 60;          // окно IP-лимита (1ч, фиксированное)
var IP_SALT = process.env.AZS_IP_SALT || "azs-v1";

// #5 мониторинг бюджета Upstash (free ~10k команд/день). Команды считаем ВЫБОРОЧНО
// (M_SAMPLE) и домножаем на 1/выборку — иначе счётчик сам съест бюджет, который стережёт.
var M_SAMPLE = 0.05;                                              // доля запросов в учёте
var CMD_ALERT_AT = Number(process.env.AZS_CMD_ALERT_AT || 8000);  // порог алерта (~80% free)
function mDay() { return new Date().toISOString().slice(0, 10); } // UTC-сутки, ключ счётчика
function justCrossed(est, inc, at) { return est >= at && (est - inc) < at; } // порог пройден именно сейчас

// ─── чистая логика агрегата (тестируется ниже без сети) ──────────────────────
// entries: { cid: '{"s":"queue","t":1699999999999}' } (как HGETALL из Redis)
// top_status — победитель по СВЕЖЕСТИ (recency-вес), не по сырому count: заправка
// пустеет за час, «нет» 5 мин назад важнее «есть» 3ч назад (ТЗ §4.5).
function aggregate(entries, now) {
  var breakdown = { yes: 0, no: 0, queue: 0, limit: 0 };
  var weight = { yes: 0, no: 0, queue: 0, limit: 0 };
  var count = 0, last = 0, totalW = 0;
  Object.keys(entries || {}).forEach(function (cid) {
    var v; try { v = JSON.parse(entries[cid]); } catch (_) { return; }
    if (!v || STATUSES.indexOf(v.s) < 0 || typeof v.t !== "number") return;
    var age = now - v.t;
    if (age > WINDOW_MS) return;                 // протухло — не считаем
    var w = 1 - age / WINDOW_MS;                 // свежесть: 1 (сейчас) → 0 (край окна)
    if (w < 0) w = 0;
    breakdown[v.s]++; weight[v.s] += w; totalW += w; count++;
    if (v.t > last) last = v.t;
  });
  var top = null, bestW = 0;
  STATUSES.forEach(function (s) { if (weight[s] > bestW) { bestW = weight[s]; top = s; } });
  var topShare = totalW > 0 ? bestW / totalW : 0;      // единодушие (доля веса победителя)
  var volume = Math.min(1, count / 3);                 // объём: 1 голос слабо, 3+ полно
  var confidence = Math.round(topShare * volume * 100) / 100;
  return {
    count: count, breakdown: breakdown, top_status: top,
    confidence: confidence, top_share: Math.round(topShare * 100) / 100,
    last_observed_at: last || null
  };
}

function validId(id) { return typeof id === "string" && /^[a-z0-9:_-]{1,48}$/i.test(id); }
function validCid(c) { return typeof c === "string" && c.length >= 3 && c.length <= 64; }

// ─── Upstash REST pipeline ───────────────────────────────────────────────────
async function upstash(commands) {
  var url = process.env.KV_REST_API_URL, token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) throw new Error("no-store");
  // #5 выборочный учёт команд бюджета: домешиваем счётчик в тот же round-trip, редко.
  var track = commands.length && Math.random() < M_SAMPLE;
  var day = track ? mDay() : null;
  var inc = track ? Math.round(commands.length / M_SAMPLE) : 0;
  var body = track ? commands.concat([
    ["INCRBY", "azs:m:cmd:" + day, String(inc)],
    ["EXPIRE", "azs:m:cmd:" + day, "172800", "NX"]
  ]) : commands;
  var r = await fetch(url.replace(/\/$/, "") + "/pipeline", {
    method: "POST",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error("upstash " + r.status);
  var out = await r.json(); // [{result:...}, ...]
  if (track) {
    var est = out[commands.length] && out[commands.length].result;      // результат INCRBY
    if (typeof est === "number" && justCrossed(est, inc, CMD_ALERT_AT)) await maybeAlert(day, est);
    out = out.slice(0, commands.length);   // команды метрики наверх не отдаём (контракт цел)
  }
  return out;
}

// #5 алерт в Telegram при пересечении порога бюджета — раз в сутки (SET NX), тихо если
// канал не настроен. RAW-fetch мимо upstash(), чтобы не пересчитывать метрику саму на себя.
async function maybeAlert(day, est) {
  try {
    var url = process.env.KV_REST_API_URL, token = process.env.KV_REST_API_TOKEN;
    var once = await fetch(url.replace(/\/$/, "") + "/pipeline", {
      method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      body: JSON.stringify([["SET", "azs:m:alerted:" + day, "1", "NX", "EX", "172800"]])
    }).then(function (r) { return r.ok ? r.json() : null; });
    if (!once || !(once[0] && once[0].result === "OK")) return;   // уже алертили сегодня
    var bot = process.env.AZS_ALERT_BOT_TOKEN, chat = process.env.AZS_ALERT_CHAT_ID;
    if (!bot || !chat) return;                                     // канал не настроен — тихо
    await fetch("https://api.telegram.org/bot" + bot + "/sendMessage", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chat,
        text: "⚠️ azs-votes: ~" + est + " команд Upstash за " + day + " (порог " + CMD_ALERT_AT + ", free ~10k/день). Проверь бюджет." })
    });
  } catch (_) { /* мониторинг не должен ронять запись голоса */ }
}

module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Cache-Control", "no-store");
  if (req.method === "OPTIONS") { res.status(204).end(); return; }

  try {
    if (req.method === "GET") {
      // ?stats=1 → лёгкий health+бюджет: число активных станций + оценка команд за сутки.
      if (req.query && req.query.stats) {
        var day = mDay();
        var s = await upstash([["GET", "azs:m:cmd:" + day], ["ZCARD", "azs:active"]]);
        res.status(200).json({
          ok: true, day: day,
          cmds_today_est: Number((s[0] && s[0].result) || 0),
          active_stations: Number((s[1] && s[1].result) || 0),
          alert_at: CMD_ALERT_AT, as_of: Date.now()
        });
        return;
      }
      // ?feed=1 → лента последних отметок {id,status,t} newest-first (для правой карточки
      // «живые отметки водителей»). Только id/статус/время — ни cid, ни IP (приватность §4).
      if (req.query && req.query.feed) {
        var fl = await upstash([["LRANGE", "azs:feed", "0", String(FEED_MAX - 1)]]);
        var rawList = (fl[0] && fl[0].result) || [], events = [];
        for (var k = 0; k < rawList.length; k++) {
          try { var ev = JSON.parse(rawList[k]);
            if (ev && ev.i && STATUSES.indexOf(ev.s) >= 0 && typeof ev.t === "number")
              events.push({ id: ev.i, status: ev.s, t: ev.t });
          } catch (_) {}
        }
        res.status(200).json({ events: events, as_of: Date.now() });
        return;
      }
      // ?active=1 → id станций со свежими (≤ окна агрегата) отметками. Клиент опрашивает
      // агрегаты только для них ∩ видимых, а не для всех видимых (на старте почти все пустые).
      if (req.query && req.query.active) {
        var t0 = Date.now();
        var az = await upstash([["ZRANGEBYSCORE", "azs:active", String(t0 - WINDOW_MS), "+inf"]]);
        res.status(200).json({ ids: (az[0] && az[0].result) || [], as_of: t0 });
        return;
      }
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
      // #2 same-origin гейт: браузер шлёт Origin на POST всегда (даже same-origin). Пускаем
      // только со своего домена (Origin.host === Host — работает и на кастомном домене/preview);
      // без Origin (curl) — уходит в IP-лимит ниже. Не панацея (Origin подделывается), но
      // режет кросс-сайт-вброс через чужие вкладки.
      var origin = req.headers.origin;
      if (origin) {
        var oh = ""; try { oh = new URL(origin).host; } catch (_) {}
        var allowed = oh && (oh === (req.headers.host || "") ||
          (process.env.AZS_ALLOWED_ORIGIN || "").split(",").indexOf(oh) >= 0);
        if (!allowed) { res.status(403).json({ error: "bad-origin" }); return; }
      }
      // #2 лимит по IP (соль-хэш + TTL, IP не храним): режет вброс ротацией cid с одного адреса.
      var ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "0";
      var iph = crypto.createHash("sha256").update(IP_SALT + ip).digest("hex").slice(0, 24);
      var ipc = await upstash([["INCR", "ripc:" + iph], ["EXPIRE", "ripc:" + iph, String(IP_WINDOW_SEC), "NX"]]);
      if ((ipc[0] && ipc[0].result) > IP_LIMIT) { res.status(429).json({ error: "rate-limited" }); return; }
      // анти-спам: 1 отметка с cid на станцию в RL_SEC (не логируем IP)
      var rl = await upstash([["SET", "rl:" + cid + ":" + id, "1", "NX", "EX", String(RL_SEC)]]);
      if (!(rl[0] && rl[0].result === "OK")) { res.status(429).json({ error: "too-soon" }); return; }
      var t = Date.now();
      var val = JSON.stringify({ s: status, t: t });
      await upstash([
        ["HSET", "av:" + id, cid, val],
        ["EXPIRE", "av:" + id, String(TTL_SEC)],
        // индекс активных станций (ZSET score=время голоса): клиент дёшево спрашивает
        // «у кого вообще есть свежие отметки», не делая HGETALL по каждой видимой станции.
        ["ZADD", "azs:active", String(t), id],
        ["ZREMRANGEBYSCORE", "azs:active", "0", String(t - TTL_SEC * 1000)], // старьё за окном TTL
        ["EXPIRE", "azs:active", String(TTL_SEC)],                           // сет тухнет, если голоса иссякли
        // лента активности: последние отметки {i:id, s:статус, t:время} для правой карточки.
        ["LPUSH", "azs:feed", JSON.stringify({ i: id, s: status, t: t })],
        ["LTRIM", "azs:feed", "0", String(FEED_MAX - 1)],
        ["EXPIRE", "azs:feed", String(TTL_SEC)]
      ]);
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
  assert.strictEqual(agg.top_status, "queue", "преобладает queue (по весу свежести)");
  assert.strictEqual(agg.last_observed_at, now - 1000);
  assert.ok(agg.confidence > 0.6 && agg.confidence <= 1, "confidence высокий при 3 свежих единодушных-ish: " + agg.confidence);
  assert.ok(agg.top_share > 0.6, "queue держит большинство веса: " + agg.top_share);
  // одна свежая отметка: top верный, но confidence низкий (помечаем «1 водитель»)
  var one = aggregate({ a: JSON.stringify({ s: "no", t: now - 1000 }) }, now);
  assert.strictEqual(one.top_status, "no");
  assert.ok(one.confidence <= 0.34, "1 голос — низкая уверенность: " + one.confidence);
  // свежее «нет» перебивает старое «есть» по весу
  var beats = aggregate({ a: JSON.stringify({ s: "yes", t: now - (WINDOW_MS * 0.9) }),
                          b: JSON.stringify({ s: "no", t: now - 1000 }) }, now);
  assert.strictEqual(beats.top_status, "no", "свежее 'нет' бьёт старое 'есть'");
  assert.deepStrictEqual(aggregate({}, now), { count: 0, breakdown: { yes: 0, no: 0, queue: 0, limit: 0 }, top_status: null, confidence: 0, top_share: 0, last_observed_at: null });
  assert.deepStrictEqual(hgetallToObj(["x", "1", "y", "2"]), { x: "1", y: "2" });
  assert.strictEqual(validId("osm-40889936"), true);
  assert.strictEqual(validId("a b"), false);
  assert.strictEqual(validCid("cid-12345"), true);
  assert.strictEqual(validCid("xx"), false);
  // #5 монитор: «порог пройден именно сейчас» + формат суток
  assert.strictEqual(justCrossed(8005, 10, 8000), true, "пересёк порог на этом инкременте");
  assert.strictEqual(justCrossed(8005, 2, 8000), false, "уже был за порогом (prev 8003)");
  assert.strictEqual(justCrossed(50, 10, 8000), false, "далеко до порога");
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(mDay()), "mDay = YYYY-MM-DD");
  console.log("[azs-votes] self-test OK");
}
