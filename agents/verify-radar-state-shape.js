#!/usr/bin/env node
/**
 * Самопроверка api/radar-state.js: гоняет handler на фиктивном upstream-payload
 * и падает, если ответ потерял поле, которое реально читает radar.html
 * (processRadar/renderPanel/renderFeed). Список полей — из ручного грепа
 * radar.html по data.*, rData.*, dd.*, m.* на момент правки C3 (2026-08-01,
 * урезание веса /api/radar-state).
 *
 * Запуск: node agents/verify-radar-state-shape.js
 */
"use strict";

const assert = require("assert");
const path = require("path");

const FIXTURE = {
  cities: [
    {
      key: "test-city|Белгородская область",
      name: "Тестгород",
      region: "Белгородская область",
      bpla: true,
      bplaDim: false,
      uab: false,
      uabDim: false,
      fpv: false,
      rocket: false,
      rocket_level: false,
      aviation: false,
      lat: 50.12345678,
      lon: 36.98765432,
      last_event_ts: 1785565129,
      source_text: "тестовое сообщение"
    }
  ],
  regions: {
    "Белгородская область": {
      bpla: false, bplaDim: false, attention: false, uab: false, uabDim: false,
      fpv: false, rocket: true, rocket_level: true, aviation: false,
      explosionOnRegion: false, bplaLaunchAnim: false, rocketOnRegion: false,
      fill: "#dc2626", last_event_ts: 1785565129, source_text: "ракетная опасность",
      pvo: { lat: 1, lon: 2 }
    }
  },
  districts: {
    "RUS.6.24_1": {
      gid_2: "RUS.6.24_1", name_ru: "Тестрайон", region_ru: "Белгородская область",
      bpla: false, bplaDim: false, attention: false, uab: false, uabDim: false,
      fpv: false, rocket: true, rocket_level: true, aviation: false,
      explosionOnRegion: false, bplaLaunchAnim: false, rocketOnRegion: true,
      fill: "#dc2626", last_event_ts: 1785565129, source_text: "ракетная опасность",
      pvo: { lat: 1, lon: 2 }
    }
  },
  route_markers: [],
  sea_markers: [],
  direction_flights: [],
  direction_arrows: [{ x: 1 }],
  poll_interval_sec: 60,
  bpla_icon_fade_sec: 10800,
  sources: [{ id: "t1", label: "Тест" }],
  recent_messages: Array.from({ length: 90 }, (_, i) => ({
    msg_id: 1000 + i,
    text: "сообщение " + i,
    ts: 1785565000 + i,
    time_label: "01.08.2026 09:1" + (i % 10) + " МСК",
    source_id: null,
    source_label: null
  }))
};

async function run() {
  global.fetch = async () => ({ ok: true, status: 200, json: async () => FIXTURE });

  const handlerPath = path.join(__dirname, "..", "api", "radar-state.js");
  delete require.cache[require.resolve(handlerPath)];
  const handler = require(handlerPath);

  let captured = null;
  let statusCode = null;
  const res = {
    setHeader() {},
    status(code) { statusCode = code; return this; },
    json(body) { captured = body; return this; },
    end() { return this; }
  };
  const req = { method: "GET", headers: { host: "npz-tactical-map.vercel.app" } };

  await handler(req, res);

  assert.strictEqual(statusCode, 200, "handler must respond 200 on happy path");
  assert.ok(captured, "handler must produce a JSON body");

  // Поля, которые ЧИТАЕТ radar.html — потеря любого из них ломает карту/панель/ленту.
  const cityKey = Object.keys(captured.cities)[0];
  assert.ok(cityKey, "cities must be non-empty");
  const city = captured.cities[cityKey];
  for (const f of ["name", "region", "bpla", "bplaDim", "uab", "uabDim", "fpv",
    "rocket", "rocket_level", "aviation", "lat", "lon", "last_event_ts", "source_text"]) {
    assert.ok(f in city, "city missing field: " + f);
  }
  // округление координат не должно съедать точность ниже 4 знаков
  assert.strictEqual(city.lat, 50.1235, "lat must be rounded to 4 decimals, got " + city.lat);
  assert.strictEqual(city.lon, 36.9877, "lon must be rounded to 4 decimals, got " + city.lon);

  const region = captured.regions["Белгородская область"];
  assert.ok(region, "regions must keep known region key");
  for (const f of ["bpla", "bplaDim", "uab", "uabDim", "fpv", "rocket", "rocket_level",
    "rocketOnRegion", "aviation", "explosionOnRegion", "last_event_ts", "source_text"]) {
    assert.ok(f in region, "region missing field: " + f);
  }
  assert.ok(!("pvo" in region), "region must NOT leak pvo (ПВО-запрет)");

  const district = captured.districts["RUS.6.24_1"];
  assert.ok(district, "districts must keep known district key");
  assert.strictEqual(district.region_ru, "Белгородская область", "district.region_ru must survive (used to bucket into region threat)");
  assert.ok(!("pvo" in district), "district must NOT leak pvo (ПВО-запрет)");

  assert.strictEqual(captured.poll_interval_sec, 60, "poll_interval_sec must survive");
  assert.ok(Array.isArray(captured.sources) && captured.sources[0].label === "Тест", "sources must survive");

  assert.ok(Array.isArray(captured.recent_messages), "recent_messages must be array");
  assert.strictEqual(captured.recent_messages.length, 60, "recent_messages must cap at 60 (frontend only ever slices 60)");
  const msg = captured.recent_messages[0];
  for (const f of ["ts", "time_label", "source_id", "source_label", "text"]) {
    assert.ok(f in msg, "message missing field: " + f);
  }

  console.log("OK: /api/radar-state shape verified (" + JSON.stringify(captured).length + " bytes for fixture payload)");
}

run().catch((e) => {
  console.error("FAIL:", e.message);
  process.exit(1);
});
