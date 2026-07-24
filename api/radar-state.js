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

  // fetch с ГАРАНТИРОВАННЫМ прерыванием по таймауту. Раньше upstream-fetch имел abort,
  // а фолбэк-fetch снапшота — НЕТ: когда из Vercel-iad подвисал ЛЮБОЙ из них, функция
  // висела >30s → карта вечно «Загрузка данных». Теперь оба fetch жёстко ограничены.
  const fetchJson = async (url, ms) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
      const r = await fetch(url, {
        headers: { Accept: "application/json", "User-Agent": "NPZ-Tactical-Map/1.0" },
        signal: ctrl.signal,
      });
      if (!r.ok) throw new Error(url + " -> " + r.status);
      return await r.json();
    } finally {
      clearTimeout(timer);
    }
  };

  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const snapshotUrl = `https://${host}/data/radar-state.json`;

  try {
    // Живой источник — но 5s хватает, а остаток бюджета Vercel-функции (10s) оставляем фолбэку.
    const data = await fetchJson("https://radar-map.ru/api/state", 5000);
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=120");
    res.setHeader("X-Radar-Src", "upstream");
    res.status(200).json(transform(data, false));
  } catch (error) {
    // Upstream флапает — отдаём последний закоммиченный слепок (agents льют каждые 10 мин),
    // чтобы карта показывала свежие данные, а не вечную «Загрузку».
    try {
      const snap = await fetchJson(snapshotUrl, 3000);
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.setHeader("Cache-Control", "s-maxage=30, stale-while-revalidate=120");
      res.setHeader("X-Radar-Src", "snapshot");
      res.status(200).json(transform(snap, true));
    } catch (fallbackError) {
      res.setHeader("Cache-Control", "s-maxage=5, stale-while-revalidate=30");
      res.setHeader("X-Radar-Src", "error");
      res.status(502).json({
        error: "radar_upstream_unavailable",
        message: error && error.message ? error.message : "Failed to fetch radar state",
        fallback_error: fallbackError && fallbackError.message ? fallbackError.message : undefined,
        fetched_at: new Date().toISOString(),
      });
    }
  }
};
