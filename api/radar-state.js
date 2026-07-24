module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }

  if (req.method !== "GET") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  // Normalize upstream (or snapshot — same shape) into our response format.
  const transform = (data, stale) => {
    const citiesDict = {};
    for (const city of (data.cities || [])) {
      const key = city.key || `${city.name}|${city.region}`;
      citiesDict[key] = {
        name: city.name,
        region: city.region,
        bpla: city.bpla || false,
        bplaDim: city.bplaDim || false,
        uab: city.uab || false,
        uabDim: city.uabDim || false,
        fpv: city.fpv || false,
        rocket: city.rocket || false,
        rocket_level: city.rocket_level || false,
        aviation: city.aviation || false,
        lat: city.lat || 0,
        lon: city.lon || 0,
        last_event_ts: city.last_event_ts || 0,
        source_text: city.source_text || ""
      };
    }

    // ПВО (air defense) НЕ отдаём — отмечать позиции ПВО на карте нельзя; вырезаем на уровне прокси
    const stripPvo = (o) => { if (o && typeof o === "object") delete o.pvo; return o; };
    const regionsSafe = data.regions || {};
    for (const r of Object.values(regionsSafe)) stripPvo(r);
    const districtsSafe = data.districts || {};
    for (const d of Object.values(districtsSafe)) stripPvo(d);
    const routeMarkers = Array.isArray(data.route_markers) ? data.route_markers.map(stripPvo) : [];
    // sea_markers / direction_flights могут нести маркеры БПЛА (над морем / в полёте) во время налётов — прокидываем
    const seaMarkers = Array.isArray(data.sea_markers) ? data.sea_markers.map(stripPvo) : [];
    const directionFlights = Array.isArray(data.direction_flights) ? data.direction_flights.map(stripPvo) : [];

    return {
      cities: citiesDict,
      regions: regionsSafe,
      districts: districtsSafe,
      route_markers: routeMarkers,
      sea_markers: seaMarkers,
      direction_flights: directionFlights,
      poll_interval_sec: data.poll_interval_sec || 60,
      recent_messages: Array.isArray(data.recent_messages) ? data.recent_messages.slice(0, 100) : [],
      sources: data.sources || [],
      direction_arrows: data.direction_arrows || [],
      bpla_icon_fade_sec: data.bpla_icon_fade_sec || 10800,
      timestamp: Date.now() / 1000,
      fetched_at: new Date().toISOString(),
      stale: !!stale
    };
  };

  try {
    // Fetch from radar-map.ru API (original data source).
    // Hard timeout ниже Vercel-лимита функции (~10s): upstream периодически отвечает 12-14s,
    // и без abort функция умирает по таймауту → 502. Лучше упасть в фолбэк на 8-й секунде.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    let upstream;
    try {
      upstream = await fetch("https://radar-map.ru/api/state", {
        headers: {
          Accept: "application/json",
          "User-Agent": "NPZ-Tactical-Map/1.0"
        },
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (!upstream.ok) throw new Error("upstream " + upstream.status);
    const data = await upstream.json();

    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=120");
    res.status(200).json(transform(data, false));
  } catch (error) {
    // Upstream флапает (reset/таймаут) — отдаём последний закоммиченный слепок,
    // чтобы карта показывала свежие данные, а не вечную «Загрузку». Слепок льёт agents/update-radar-state.py.
    try {
      const host = req.headers["x-forwarded-host"] || req.headers.host;
      const snapRes = await fetch(`https://${host}/data/radar-state.json`, {
        headers: { Accept: "application/json" },
      });
      if (!snapRes.ok) throw new Error("snapshot " + snapRes.status);
      const snap = await snapRes.json();
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.setHeader("Cache-Control", "s-maxage=30, stale-while-revalidate=120");
      res.status(200).json(transform(snap, true));
    } catch (fallbackError) {
      res.setHeader("Cache-Control", "s-maxage=5, stale-while-revalidate=30");
      res.status(502).json({
        error: "radar_upstream_unavailable",
        message: error && error.message ? error.message : "Failed to fetch radar state",
        fallback_error: fallbackError && fallbackError.message ? fallbackError.message : undefined,
        fetched_at: new Date().toISOString(),
      });
    }
  }
};
