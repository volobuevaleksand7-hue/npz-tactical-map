#!/usr/bin/env python3
"""Публикация объектных НПЗ-страниц из предсобранных черновиков drafts/npz/.

В отличие от rocket/fuel, контент НПЗ-страниц уникален и пишется заранее
(черновик в drafts/npz/<slug>.html). Этот скрипт только выкатывает готовый
черновик в прод: двигает файл, регистрирует в реестре/sitemap, гоняет nav+IA,
коммитит и пушит. Идемпотентно.

  python3 agents/publish-npz.py slavneft-yanos
  python3 agents/publish-npz.py --all           # все черновики из drafts/npz/, ещё не в реестре
  python3 agents/publish-npz.py slavneft-yanos --dry-run

Метаданные реестра — из REGISTRY (готовые строки ТЗ tz-articles-2026-07-08).
created проставляется датой публикации. Тип object → в топ-меню НЕ попадает
(живёт под /refineries), поэтому LABELS/HUB в build-nav не нужны.
"""
import sys, subprocess, pathlib, datetime, json, os

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REG = ROOT / "data" / "seo-topics.jsonl"
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://npz-tactical-map.vercel.app"
DRAFTS = ROOT / "drafts" / "npz"

REGISTRY = {
    "slavneft-yanos": {
        "primary_kw": "нпз янос",
        "keywords": ["удар по ярославскому нпз", "ярославль нпз бпла",
                     "ярославский нпз бпла", "ярославский нпз атака бпла",
                     "дефицит бензина в ярославле"],
        "note": "ЯНОС/Славнефть; удар 8 мая в strikes.json отдельной записью не отражён — "
                "формулировка «по данным открытых источников».",
    },
    "kujbyshevskij-npz": {
        "primary_kw": "куйбышевский нпз бпла",
        "keywords": ["куйбышевский нпз атака бпла", "удар по куйбышевскому нпз",
                     "дефицит бензина в самаре", "самара бензин по талонам"],
        "note": "НЕ путать с Новокуйбышевским НПЗ — отдельный завод, отдельная будущая страница.",
    },
    "ryazanskij-npz": {
        "primary_kw": "рязанский нпз бпла",
        "keywords": ["рязанский нпз атака бпла", "удар по рязанскому нпз",
                     "дефицит бензина в рязани", "дефицит бензина в рязанской области"],
        "note": "в strikes.json нет записей по заводу — хроника только из fuel-state.json, "
                "не выдумывать.",
    },
    "saratovskij-npz": {
        "primary_kw": "саратовский нпз атака дронов",
        "keywords": ["атака на саратовский нпз", "нпз в саратове атака беспилотников",
                     "саратовский нпз атака бпла", "удар по нпз саратов",
                     "дефицит топлива в саратове"],
        "note": "Роснефть, 7 млн т/год, остановлен с 08.07.2026. Первый удар 31 мая в "
                "strikes.json отдельной записью не отражён — «по данным открытых источников».",
    },
    "lukojl-norsi": {
        "primary_kw": "лукойл норси удар",
        "keywords": ["нпз кстово удар", "кстовский нпз бпла", "норси кстово",
                     "удар по нпз в кстово", "дефицит бензина в нижегородской области"],
        "note": "Лукойл, 17 млн т/год, остановлен с 02.07.2026 (АВТ-6). Даты возобновления "
                "переработки в открытых источниках нет — не выдумывать.",
    },
    "taneko-npz": {
        "primary_kw": "танеко нпз атака",
        "keywords": ["атака на танеко", "удар по нпз танеко", "танеко нижнекамск бпла",
                     "нпз танеко пожар", "дефицит бензина в татарстане"],
        "note": "Татнефть, ~17 млн т/год, Нижнекамск. Серия ударов 12/16.06 и 08/10.07. "
                "В economy.json ТАНЕКО среди 10 полностью остановленных; в fuel-state — partial "
                "~20% с 08.07 (взято per-object значение). ТАИФ-НК — отдельный сосед, своя страница.",
    },
    "bashneft-ufa": {
        "primary_kw": "уфимский нпз удар",
        "keywords": ["удар по уфимскому нпз", "башнефть новойл атака бпла", "уфанефтехим удар",
                     "нпз уфа пожар", "дефицит бензина в башкортостане"],
        "note": "Уфимский узел Башнефть/Роснефть (УНПЗ + Новойл 7,3 + Уфанефтехим 9), ~24 млн т/год. "
                "Удары 25.06/01.07/08.07; fuel-state partial ~40% с 08.07; дефицит Башкортостан — severe.",
    },
    "taif-nk": {
        "primary_kw": "нижнекамский нпз атака",
        "keywords": ["таиф-нк удар", "таиф-нк нижнекамск бпла", "удар по таиф-нк",
                     "нпз нижнекамск бпла", "дефицит бензина в татарстане"],
        "note": "ТАИФ-НК, Нижнекамск, ~8 млн т/год (справочно — в data мощности нет). Прямое "
                "упоминание в ударе только 12.06 (с ТАНЕКО); отдельного статуса в fuel-state нет — "
                "страница честно тоньше, повреждения не выдумывать. Не путать с ТАНЕКО.",
    },
    "ilskij-npz": {
        "primary_kw": "ильский нпз удар",
        "keywords": ["удар по ильскому нпз", "ильский нпз бпла", "пожар на ильском нпз",
                     "нпз краснодарский край атака", "дефицит бензина в краснодарском крае"],
        "note": "Ильский НПЗ, ИНК/РНГО, Краснодарский край, 6,6 млн т/год (крупнейший НПЗ юга РФ). "
                "Удары 11.06 + 10.07 (пожар от обломков) + 11.07 (ЭЛОУ-АВТ-5); fuel-state partial "
                "~40% с 10.07. Дефицит Краснодар — severe (лимит 30 л, очереди до 7ч). Часть "
                "источников (TMT) называют оператором Роснефть — в data канон ИНК/РНГО.",
    },
    "tuapsinskij-npz": {
        "primary_kw": "туапсинский нпз",
        "keywords": ["туапсинский нпз статус", "туапсинский нпз остановлен",
                     "нпз туапсе", "роснефть туапсе нпз",
                     "дефицит бензина в краснодарском крае"],
        "note": "Роснефть, 12 млн т/год, Туапсе (Краснодарский край, у моря), экспортный. "
                "Остановлен с 16.04.2026 (Reuters); рестарт ~ноя-дек 2026 (оценка Rosneft/OilPrice/"
                "QCIntel). Прямых ударов по заводу в strikes.json НЕТ — хроника честно тоньше, "
                "детали не выдумывать.",
    },
    "syzranskij-npz": {
        "primary_kw": "сызранский нпз удар",
        "keywords": ["удар по сызранскому нпз", "сызранский нпз бпла",
                     "атака на сызранский нпз", "нпз сызрань",
                     "дефицит бензина в самарской области"],
        "note": "Роснефть, 8.5 млн т/год, Сызрань Самарской обл. Удары 21.05 и 12.07.2026 "
                "(ЭЛОУ-АВТ-5, АВТ-6); fuel-state down 0% с 12.07. Самарский кластер Роснефти "
                "(с Куйбышевским и Новокуйбышевским). Источник united24media.",
    },
    "afipskij-npz": {
        "primary_kw": "афипский нпз удар",
        "keywords": ["удар по афипскому нпз", "афипский нпз бпла", "пожар на афипском нпз",
                     "нпз краснодарский край атака", "дефицит бензина в краснодарском крае"],
        "note": "ГК Сафмар, 9 млн т/год, пгт Афипский Краснодарского края. Удары 11.06 "
                "(Краснодар/обломки) и 14.07.2026 (пожар, 1 пострадавший); fuel-state partial "
                "~40% с 14.07. Источник moscowtimes 14.07. Кубанский кластер (с Ильским, Туапсинским).",
    },
    "kinef": {
        "primary_kw": "кинеф удар",
        "keywords": ["нпз кириши бпла", "киришинефтеоргсинтез атака", "удар по кинеф",
                     "нпз в киришах", "дефицит бензина в ленинградской области",
                     "дефицит бензина в санкт-петербурге"],
        "note": "Кинеф (Киришинефтеоргсинтез), Сургутнефтегаз, Кириши Ленинградской обл., "
                "20,1 млн т/год — 2-й НПЗ РФ и крупнейший в европейской части (~7% переработки). "
                "fuel-state: partial ~30% с 05.05.2026, повреждены 3 из 4 CDU (верификация 21.06), "
                "источник meduza 05.05. Прямого удара по заводу в strikes.json НЕТ (только регион: "
                "порты Усть-Луга/Высоцк/НОВАТЭК 06-10.07 — отдельные объекты, не конфлировать). "
                "Дефицит: СПб/Ленобласть medium, Псков high, Новгород medium.",
    },
    "volgogradskij-npz": {
        "primary_kw": "волгоградский нпз статус",
        "keywords": ["волгоградский нпз лукойл", "работает ли волгоградский нпз", "нпз волгоград бпла",
                     "волгоградский нпз мощность", "дефицит бензина в волгоградской области"],
        "note": "Лукойл, Волгоградская обл., 15,7 млн т/год. operational 100%, fuel-state: "
                "«нет подтверждённых данных об ударе». Самая тонкая страница пачки — честно "
                "справочная, с явным disclaimer, что заводу удара не было (не путать с Котово/"
                "«Титан-Баррикады» — другие объекты региона).",
    },
    "angarskij-npz": {
        "primary_kw": "ангарский нпз статус",
        "keywords": ["ангарский нпз роснефть", "работает ли ангарский нпз", "нпз ангарск",
                     "ангарский нпз мощность", "дефицит бензина в иркутской области"],
        "note": "Роснефть, Иркутская обл., 10,2 млн т/год. operational 100%, ударов в data нет. "
                "Единственный из 32 заводов с попаданием в топ-500 Вебмастера (45 показов, 0 кликов). "
                "Угол страницы — завод работает штатно, но регион под жёстким дефицитом "
                "(deficit_regions: Иркутская обл. high, патрули очередей, 18ч ожидания).",
    },
    "novokujbyshevskij-npz": {
        "primary_kw": "новокуйбышевский нпз атака бпла",
        "keywords": ["удар по новокуйбышевскому нпз", "новокуйбышевский нпз статус",
                     "новокуйбышевский нпз роснефть", "дефицит бензина в самарской области",
                     "новокуйбышевский нпз не путать с куйбышевским"],
        "note": "Роснефть, Самарская обл., 8,8 млн т/год. Удар 18.04 (АВТ-11+АВТ-9), fuel-state "
                "partial ~40%. ⚠️ НЕ путать с Куйбышевским НПЗ (/npz/kujbyshevskij-npz) — отдельный "
                "завод, третий в Самарской группе с Сызранским.",
    },
    "astrahanskij-gpz": {
        "primary_kw": "астраханский гпз статус",
        "keywords": ["астраханский гпз работает", "астраханский газоперерабатывающий завод",
                     "бензин по чётным нечётным дням астрахань", "дефицит бензина в астрахани",
                     "астраханский гпз газпром"],
        "note": "Газпром переработка, Астраханская обл., 12 млн т/год (ГПЗ, не классический НПЗ). "
                "operational 100%, ударов нет. Угол — завод работает, но регион с 09.07 живёт по "
                "системе чётных/нечётных дней продажи бензина (deficit_regions: Астраханская обл. "
                "high, источник finance.mail.ru).",
    },
}


def sh(cmd, **kw):
    print("$", " ".join(cmd)); return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def published():
    urls = set()
    for l in REG.read_text(encoding="utf-8").splitlines():
        if l.strip():
            urls.add(json.loads(l).get("url"))
    return urls


def add_registry(slug, today):
    url = f"/npz/{slug}"
    if url in published():
        print("реестр: уже есть", url); return
    r = REGISTRY[slug]
    entry = {"url": url, "type": "object", "primary_kw": r["primary_kw"],
             "keywords": r["keywords"], "created": today, "status": "live",
             "note": r["note"]}
    with REG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("реестр: добавлено", url)


def add_sitemap(slug, today):
    loc = f"{SITE}/npz/{slug}"
    xml = SITEMAP.read_text(encoding="utf-8")
    if loc in xml:
        print("sitemap: уже есть"); return
    block = (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n"
             f"    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n"
             f'    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>\n  </url>\n')
    SITEMAP.write_text(xml.replace("</urlset>", block + "</urlset>", 1), encoding="utf-8")
    print("sitemap: добавлено", loc)


def move_draft(slug):
    src = DRAFTS / f"{slug}.html"
    dst = ROOT / "npz" / f"{slug}.html"
    if not src.exists():
        if dst.exists():
            print("черновик уже выкачен:", dst.relative_to(ROOT)); return
        sys.exit(f"нет черновика {src.relative_to(ROOT)} и нет {dst.relative_to(ROOT)}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    src.unlink()
    print(f"выкачено: {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")


def main(argv):
    dry = "--dry-run" in argv
    if "--all" in argv:
        pub = published()
        slugs = [p.stem for p in sorted(DRAFTS.glob("*.html"))
                 if f"/npz/{p.stem}" not in pub and p.stem in REGISTRY]
        if not slugs:
            print("нет невыпущенных черновиков в drafts/npz/"); return
    else:
        slugs = [a for a in argv if a in REGISTRY]
        if not slugs:
            sys.exit(f"укажи slug или --all. Известные: {', '.join(REGISTRY)}")

    today = datetime.date.today().isoformat()
    for slug in slugs:
        move_draft(slug)
        add_registry(slug, today)
        add_sitemap(slug, today)
    sh([sys.executable, str(HERE / "build-nav.py")])
    sh([sys.executable, str(HERE / "check-ia.py")])

    if dry:
        print("--dry-run: коммит/пуш пропущены"); return

    # точечная выкладка: только выпускаемые артефакты, НИКОГДА git add -A —
    # он засасывал в коммит публикации весь untracked-мусор дерева.
    # -u берёт все изменённые/удалённые ОТСЛЕЖИВАЕМЫЕ файлы: реестр, sitemap,
    # nav/footer-правки build-nav.py (все html уже в репо) и удаление drafts/npz/<slug>.
    # Новые npz/<slug>.html ещё не отслеживаются — добавляем явно.
    sh(["git", "add", "-u"])
    sh(["git", "add", "--"] + [f"npz/{s}.html" for s in slugs])
    names = ", ".join(f"/npz/{s}" for s in slugs)
    msg = (f"seo: НПЗ-страница ({names})\n\n"
           f"Выкачено из drafts/npz/ (контент по ТЗ tz-articles-2026-07-08 + data/*),\n"
           f"нейтральный тон, 3 JSON-LD, крошки на /refineries.\n\n"
           f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True,
                   env={**os.environ, "ALLOW_FRONTEND_RELEASE": "1"})
    # безопасный пуш (протокол HERMES.md §0): дерево чистое после commit →
    # plain --rebase, НИКОГДА --autostash (он молча сносит чужие uncommitted правки)
    for _ in range(4):
        if subprocess.run(["git", "push", "origin", "main"], cwd=ROOT).returncode == 0:
            break
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
    else:
        raise RuntimeError("push отклонён после 4 попыток — синхронизировать вручную")
    print(f"\n✅ опубликовано: {names}\n"
          f"⚠️ добавить обратную ссылку-карточку с /refineries и из ближайшей сводки (ручной шаг реоптa).")


if __name__ == "__main__":
    main(sys.argv[1:])
