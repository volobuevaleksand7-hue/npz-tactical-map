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

  try {
    // Fetch from radar-map.ru API (original data source)
    const upstream = await fetch("https://radar-map.ru/api/state", {
      headers: { 
        Accept: "application/json",
        "User-Agent": "NPZ-Tactical-Map/1.0"
      },
    });

    const data = await upstream.json();
    
    // Convert cities from array to dict format
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
    const regionsSafe = data.regions || {};
    for (const r of Object.values(regionsSafe)) { if (r && typeof r === "object") delete r.pvo; }

    // Build response in our format
    const result = {
      cities: citiesDict,
      regions: regionsSafe,
      poll_interval_sec: data.poll_interval_sec || 60,
      recent_messages: Array.isArray(data.recent_messages) ? data.recent_messages.slice(0, 100) : [],
      sources: data.sources || [],
      direction_arrows: data.direction_arrows || [],
      bpla_icon_fade_sec: data.bpla_icon_fade_sec || 10800,
      timestamp: Date.now() / 1000,
      fetched_at: new Date().toISOString()
    };

    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=120");
    res.status(200).json(result);
  } catch (error) {
    res.setHeader("Cache-Control", "s-maxage=5, stale-while-revalidate=30");
    res.status(502).json({
      error: "radar_upstream_unavailable",
      message: error && error.message ? error.message : "Failed to fetch radar state",
      fetched_at: new Date().toISOString(),
    });
  }
};
