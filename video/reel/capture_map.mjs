// Скриншот главной карты сайта (Leaflet, OSM-тайлы) в высоком разрешении + пиксельные
// координаты выбранных ударов. Хром сайта (шапка, панели, контролы) прячется — остаётся карта.
//   node capture_map.mjs <targets.json> <out.jpg> <out-points.json>
// targets.json: {"bounds":[[lat,lon],[lat,lon]], "points":[{"id":..,"lat":..,"lon":..}], "url": "..."}
import fs from "node:fs";
import puppeteer from "puppeteer-core";

const [tFile, outImg, outJson] = process.argv.slice(2);
if (!outJson) { console.error("usage: node capture_map.mjs targets.json out.jpg out.json"); process.exit(2); }
const T = JSON.parse(fs.readFileSync(tFile, "utf8"));
const URL_ = T.url || "https://npz-tactical-map.vercel.app/";
const CSS_W = 2160, CSS_H = 3840, DPR = 1.5;   // кадр 3240×5760 px, 9:16
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new",
  args: ["--no-first-run", "--disable-extensions", "--hide-scrollbars"] });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: CSS_W, height: CSS_H, deviceScaleFactor: DPR });
  // экземпляр карты живёт в замыкании app.js — перехватываем L.map при загрузке Leaflet
  await page.evaluateOnNewDocument(() => {
    let _L;
    Object.defineProperty(window, "L", { configurable: true, get: () => _L, set: v => {
      _L = v;
      if (v && v.map && !v.map.__hooked) {
        const orig = v.map;
        v.map = function (...a) { const m = orig.apply(this, a); (window.__maps = window.__maps || []).push(m); return m; };
        v.map.__hooked = true;
      }
    } });
    try { localStorage.setItem("npz-theme", "light"); } catch (e) {}
  });
  await page.goto(URL_, { waitUntil: "networkidle2", timeout: 90000 });
  await page.waitForFunction(() => window.__maps && window.__maps.length &&
    document.querySelectorAll("#map .leaflet-marker-icon").length > 5, { timeout: 60000 });
  await new Promise(r => setTimeout(r, 2500)); // регионы/удары догружаются
  await page.addStyleTag({ content: `
    body > *:not(main):not(.view):not(#app):not(script) { }
    #map { position:fixed !important; left:0 !important; top:0 !important; width:100vw !important; height:100vh !important; z-index:2147483000 !important; margin:0 !important; border-radius:0 !important; }
    #map .leaflet-control-container, .leaflet-popup, .leaflet-tooltip { display:none !important; }
  `});
  const pts = await page.evaluate(async (T, DPR) => {
    // всё, что не карта и не её предки, — прячем
    const map = document.getElementById("map");
    const keep = new Set(); for (let e = map; e; e = e.parentElement) keep.add(e);
    document.querySelectorAll("body *").forEach(e => {
      if (!keep.has(e) && !map.contains(e) && !e.contains(map)) e.style.setProperty("visibility", "hidden", "important");
    });
    const m = window.__maps[0];
    m.closePopup();
    m.options.zoomSnap = 0;
    m.invalidateSize({ animate: false });
    m.fitBounds(T.bounds, { animate: false, padding: [0, 0] });
    await new Promise(r => setTimeout(r, 600));
    // ждём тайлы
    const t0 = Date.now();
    while (Date.now() - t0 < 30000) {
      const imgs = [...document.querySelectorAll("#map .leaflet-tile")];
      if (imgs.length && imgs.every(i => i.complete && i.naturalWidth)) break;
      await new Promise(r => setTimeout(r, 400));
    }
    await new Promise(r => setTimeout(r, 1500));
    const size = m.getSize();
    return { zoom: m.getZoom(), w: Math.round(size.x * DPR), h: Math.round(size.y * DPR),
      points: T.points.map(p => { const c = m.latLngToContainerPoint([p.lat, p.lon]);
        return { ...p, x: +(c.x * DPR).toFixed(1), y: +(c.y * DPR).toFixed(1) }; }) };
  }, T, DPR);
  await page.screenshot({ path: outImg, type: "jpeg", quality: 90 });
  fs.writeFileSync(outJson, JSON.stringify(pts, null, 1));
  console.log(`capture: ${outImg} ${pts.w}x${pts.h} zoom ${pts.zoom.toFixed(2)}, ${pts.points.length} точек`);
} finally {
  await browser.close();
}
