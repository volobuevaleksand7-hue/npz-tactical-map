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
  // ponytail: сантиметры на карте городов не нужны — 4 знака после запятой (~11м)
  // с запасом покрывает точность маркера на радаре; режет ~2-3 байта/координата.
  const round4 = (n) => Math.round((n || 0) * 10000) / 10000;

  // Общие для region/district поля угроз, которые реально читает radar.html
  // (грепнуто по rData./dd. в processRadar): остальное (attention, bplaLaunchAnim,
  // fill, ПВО) фронт не трогает — не отдаём.
  const threatFields = (o) => ({
    bpla: o.bpla || false,
    bplaDim: o.bplaDim || false,
    uab: o.uab || false,
    uabDim: o.uabDim || false,
    fpv: o.fpv || false,
    rocket: o.rocket || false,
    rocket_level: o.rocket_level || false,
    rocketOnRegion: o.rocketOnRegion || false,
    aviation: o.aviation || false,
    explosionOnRegion: o.explosionOnRegion || false,
    last_event_ts: o.last_event_ts || 0,
    source_text: o.source_text || ""
  });

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
        lat: round4(city.lat),
        lon: round4(city.lon),
        last_event_ts: city.last_event_ts || 0,
        source_text: city.source_text || ""
      };
    }

    const regionsSafe = {};
    for (const [name, r] of Object.entries(data.regions || {})) {
      regionsSafe[name] = threatFields(r || {});
    }
    const districtsSafe = {};
    for (const [key, d0] of Object.entries(data.districts || {})) {
      const d = d0 || {};
      districtsSafe[key] = Object.assign({ region_ru: d.region_ru }, threatFields(d));
    }

    // ПВО (air defense) НЕ отдаём — отмечать позиции ПВО на карте нельзя; вырезаем на уровне прокси
    const stripPvo = (o) => { if (o && typeof o === "object") delete o.pvo; return o; };
    const routeMarkers = Array.isArray(data.route_markers) ? data.route_markers.map(stripPvo) : [];
    // sea_markers / direction_flights могут нести маркеры БПЛА (над морем / в полёте) во время налётов — прокидываем
    const seaMarkers = Array.isArray(data.sea_markers) ? data.sea_markers.map(stripPvo) : [];
    const directionFlights = Array.isArray(data.direction_flights) ? data.direction_flights.map(stripPvo) : [];

    // recent_messages: фронт (renderFeed) рендерит только первые 60 — msg_id никогда не читает
    const messages = Array.isArray(data.recent_messages) ? data.recent_messages.slice(0, 60) : [];
    const recentMessages = messages.map((m) => ({
      ts: m.ts || 0,
      time_label: m.time_label || "",
      source_id: m.source_id || null,
      source_label: m.source_label || null,
      text: m.text || ""
    }));

    return {
      cities: citiesDict,
      regions: regionsSafe,
      districts: districtsSafe,
      route_markers: routeMarkers,
      sea_markers: seaMarkers,
      direction_flights: directionFlights,
      poll_interval_sec: data.poll_interval_sec || 60,
      recent_messages: recentMessages,
      sources: data.sources || [],
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
    // 🔴 Заголовки Cache-Control задаются ЗДЕСЬ, по ветке. Раньше их глушил статический
    // заголовок в vercel.json (s-maxage=10) — он перекрывает всё, что ставит функция, и
    // ветвление было мёртвым кодом: edge ревалидировал раз в 10 с и на каждом промахе платил
    // полный таймаут упавшего upstream (замер 29.07: MISS 6,2 с при лимите функции 10 с).
    // 2,5 с хватает живому upstream с запасом; когда он флапает — быстрее уходим на снапшот.
    const data = await fetchJson("https://radar-map.ru/api/state", 2500);
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=600");
    res.setHeader("X-Radar-Src", "upstream");
    res.status(200).json(transform(data, false));
  } catch (error) {
    // Upstream флапает — отдаём последний закоммиченный слепок (agents льют каждые 10 мин),
    // чтобы карта показывала свежие данные, а не вечную «Загрузку».
    try {
      const snap = await fetchJson(snapshotUrl, 3000);
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      // Снапшот всё равно обновляется агентами раз в ~10 мин — держать его в edge 10 с не было
      // смысла, только лишние промахи с полным таймаутом. 60 с + длинный SWR: пока upstream
      // лежит, пользователь получает мгновенный ответ, а обновление идёт в фоне.
      res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=600");
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
