#!/usr/bin/env python3
"""Единый навбар + хаб для всех статей/лендингов — генерится из data/seo-topics.jsonl.

Источник правды один: реестр. Добавил страницу в seo-topics.jsonl (+ подписи в
LABELS/HUB ниже, если хочешь красиво) → запусти `python3 agents/build-nav.py` — и
она сама появляется в ТРЁХ местах:
  1) выпадашка «Аналитика» на всех лендингах (news-nav),
  2) дропдаун «АНАЛИТИКА» на ГЛАВНОЙ карте (index.html, tab-dropdown-menu),
  3) каталог-хаб /analytics (analytics-grid).
Это убивает сирот навсегда: забыть добавить пункт в меню руками уже нельзя.
Проверяет целостность `agents/check-ia.py`.

⚠️ index.html — фронтенд-ядро: его коммит требует ALLOW_FRONTEND_RELEASE=1.

Тип страницы (`type` в реестре) → группа меню:
  region → Регионы · region + /raketnaya-opasnost-* → свёрнутый блок «Ракетная опасность» ·
  explainer → Топливо · forecast → Прогноз · reference → Справочники · tool → Карты ·
  object(/npz/*) → свёрнутый блок «НПЗ по заводам» (в меню; в хабе /analytics НЕ дублируется —
  там уже есть /refineries со списком всех заводов, см. HUB_EXCLUDE_GROUPS).
"""
import json, re, pathlib, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG  = ROOT / "data" / "seo-topics.jsonl"

# Верхний уровень (порядок важен): url, emoji, label
TOP      = [("/", "🗺️", "Карта НПЗ"), ("/news", "📰", "Сводки"), ("/radar", "📡", "Радар БПЛА")]
TOP_TAIL = [("/sources", "📚", "Источники")]

ROCKET_PREFIX = "/raketnaya-opasnost-"


def is_rocket(r):
    return r["url"].startswith(ROCKET_PREFIX)


# Группы выпадашки: (заголовок, предикат(row)->bool, collapse). Порядок = порядок в меню и на хабе.
# collapse=True → группа рисуется свёрнутым <details> (город-лонгтейлы не раздувают меню).
GROUPS = [
    ("Регионы",            lambda r: r.get("type") == "region" and not is_rocket(r), False),
    ("Ракетная опасность", is_rocket,                                                True),
    ("Топливо",            lambda r: r.get("type") == "explainer",                   False),
    ("Прогноз",            lambda r: r.get("type") == "forecast",                    False),
    ("Справочники",        lambda r: r.get("type") == "reference",                   False),
    ("Карты",              lambda r: r.get("type") == "tool",                        False),
    ("НПЗ по заводам",     lambda r: r.get("type") == "object",                       True),
]

# Свёрнутые (collapse=True) группы: свои эмодзи заголовка <summary> и эмодзи пункта —
# было захардкожено под единственную группу «Ракетная опасность» (🚀 / 📍), теперь общий словарь.
COLLAPSE_EMOJI = {
    "Ракетная опасность": ("🚀", "📍"),
    "НПЗ по заводам":     ("🏭", "🛢️"),
}
# Эти группы сортируются по алфавиту подписи, а не по порядку строк в реестре
# (реестр = хронология публикации, для 34+ заводов это нечитаемо).
GROUP_SORT_ALPHA = {"НПЗ по заводам"}

# Вложенные подгруппы ВНУТРИ группы (напр. «Топливо», «Справочники») — тот же паттерн
# <details class="nav-drop-sub">, что уже отрисован для верхнеуровневых collapse-групп
# («Ракетная опасность», «НПЗ по заводам»), просто без своего пункта в GROUPS. Пункт
# группы, не попавший ни в одну подгруппу, остаётся видимым пином прямо под заголовком
# группы (напр. /deficit — «Почему нет бензина»).
#
# 🔴 ПРАВИЛО ДЛЯ НОВЫХ СТАТЕЙ. Ручной список URL здесь держать НЕ надо — иначе каждая
# новая страница молча падает пином в корень группы и меню снова становится портянкой
# (так и выросли 15 пунктов подряд в «Топливе»). Страница попадает в подгруппу так:
#   1) поле "group" в data/seo-topics.jsonl — приоритет; ставь его при заведении страницы;
#   2) если поля нет — тематический паттерн ниже по url + primary_kw + keywords;
#   3) не совпало ничего — остаётся видимым пином (это осознанный запасной вариант,
#      сироты по-прежнему невозможны).
# Заводя новую подгруппу, добавляй сюда строку с паттерном, а не перечень адресов.
SUBGROUPS = {
    "Топливо": [
        ("⛽", "Где заправиться",
         r"где (найти|есть|заправить)|на трассе|закрыл|ai-?95|аи-?95|дизел|газ на азс"),
        ("🚦", "Обстановка на АЗС",
         r"очеред|драк|конфликт|ажиотаж|талон|канистр|лимит|паник"),
        ("🚢", "Нефть и экспорт",
         r"танкер|теневой флот|экспорт|азовск|голод|эмбарго|нефтян(ой|ые) доход"),
    ],
    "Справочники": [
        ("📦", "Склады маркетплейсов",
         r"wildberries|вайлдберр|ozon|озон|склад|маркетплейс|фулфилмент"),
        ("🏭", "Справочники по НПЗ",
         r"нпз|нефтеперераб|завод|переработк"),
    ],
}


def subgroup_for(row, title):
    """Подгруппа страницы внутри группы title: явное поле реестра → тематический паттерн."""
    subs = SUBGROUPS.get(title, [])
    want = (row.get("group") or "").strip().lower()
    if want:
        for emoji, subtitle, _ in subs:
            if subtitle.lower() == want:
                return subtitle
        return None            # указана несуществующая подгруппа — ловит check_subgroup_field()
    blob = " ".join([row.get("url", ""), row.get("primary_kw", "")] + list(row.get("keywords") or [])).lower()
    for emoji, subtitle, pattern in subs:
        if re.search(pattern, blob):
            return subtitle
    return None


def split_subgroups(title, picked):
    """picked -> (pinned, [(emoji, subtitle, items), ...]). Подгруппа появляется, только
    если в неё реально попала хоть одна live-страница; страница, не подошедшая ни под
    одно правило, остаётся видимым пином (сироты невозможны, как и везде в этом файле)."""
    used, subs = set(), []
    for emoji, subtitle, _ in SUBGROUPS.get(title, []):
        items = [r for r in picked if subgroup_for(r, title) == subtitle]
        if items:
            subs.append((emoji, subtitle, items))
            used.update(r["url"] for r in items)
    pinned = [r for r in picked if r["url"] not in used]
    return pinned, subs


# Подписи пунктов меню: url -> (emoji, label). Нет в списке → берётся primary_kw.
LABELS = {
    "/crimea":            ("🗺", "Крым"),
    "/krasnodar":         ("🌴", "Краснодар"),
    "/moskva":            ("🏙", "Москва"),
    "/raketnaya-opasnost-volgograd": ("🚀", "Ракетная опасность: Волгоград"),
    "/raketnaya-opasnost-ulyanovsk": ("🚀", "Ракетная опасность: Ульяновск"),
    "/raketnaya-opasnost-kazan":     ("🚀", "Ракетная опасность: Казань"),
    "/raketnaya-opasnost-omsk":      ("🚀", "Ракетная опасность: Омск"),
    "/raketnaya-opasnost-cheboksary": ("🚀", "Ракетная опасность: Чебоксары"),
    "/raketnaya-opasnost-moskovskaya-oblast": ("🚀", "Ракетная опасность: Московская обл."),
    "/raketnaya-opasnost-penza":     ("🚀", "Ракетная опасность: Пенза"),
    "/raketnaya-opasnost-samara":    ("🚀", "Ракетная опасность: Самара"),
    "/deficit":           ("⛽", "Почему нет бензина"),
    "/talony":            ("🎫", "Бензин по талонам"),
    "/benzin-na-trasse":  ("🛣️", "Бензин на трассе"),
    "/gde-dizel":         ("🛢️", "Где найти дизель"),
    "/crisis":            ("🔥", "Прогноз кризиса"),
    "/attacks":           ("💥", "Хроника ударов"),
    "/refineries":        ("🏭", "Список НПЗ · все заводы"),
    "/npz-lukojla":       ("🛢️", "НПЗ Лукойла"),
    "/npz-rosnefti":      ("🛢️", "НПЗ Роснефти"),
    "/npz-gazprom-nefti": ("🛢️", "НПЗ Газпром нефти"),
    "/volna-dronov":      ("🛩", "Волна дронов сейчас"),
    "/karta-benzina-krym": ("🗺️", "Карта бензина Крым"),
    "/karta-bpla":          ("📡", "Карта БПЛА"),
    "/karta-azs":           ("⛽", "Карта АЗС"),
    "/azs-ryadom":          ("📍", "АЗС рядом со мной"),
    "/help":              ("❓", "Как пользоваться"),
    "/metodologiya":      ("🔬", "Методология"),
    # без записи здесь label_for берёт SEO-ключ и делает .capitalize() — а он гасит все
    # остальные заглавные («удары по азовскому морю» → «Удары по азовскому морю»)
    "/udary-azovskoe-more":  ("💥", "Удары по Азовскому морю"),
    "/tankery-azovskoe-more": ("🚢", "Танкеры в Азовском море"),
    "/vozmozhen-li-golod":   ("🌾", "Будет ли голод в России"),
    "/udary-po-tankeram":    ("🚢", "Удары по танкерам теневого флота"),
    "/udar-po-skladam-wildberries":       ("📦", "Удар по складам Wildberries"),
    "/ataki-na-sklady-wildberries-hronika": ("🗓", "Атаки на склады Wildberries: хроника"),
    "/kompensacii-wildberries-posle-udara": ("💸", "Компенсации Wildberries после ударов"),
    "/raketnaya-opasnost-tambovskaya-oblast": ("🚀", "Ракетная опасность: Тамбовская обл."),
    "/raketnaya-opasnost-sverdlovskaya-oblast": ("🚀", "Ракетная опасность: Свердловская обл."),
    "/raketnaya-opasnost-rostovskaya-oblast": ("🚀", "Ракетная опасность: Ростовская обл."),
    "/raketnaya-opasnost-kirovskaya-oblast": ("🚀", "Ракетная опасность: Кировская обл."),
    "/raketnaya-opasnost-tyumenskaya-oblast": ("🚀", "Ракетная опасность: Тюменская обл."),
    "/raketnaya-opasnost-ryazanskaya-oblast": ("🚀", "Ракетная опасность: Рязанская обл."),
    "/skolko-skladov-wildberries-ozon": ("📦", "Сколько складов у ВБ и Озон"),
    "/kakie-sklady-wildberries-ostalis": ("📋", "Какие склады ВБ и Ozon остались"),
    # Без записи здесь пункт показывается сырым SEO-ключом («сгорел склад wildberries что
    # делать») и заглушкой 📄 — вычитка подписей обязательна, см. check-ia.py: он ругается
    # на каждую live-страницу без ручной подписи.
    "/gde-est-benzin":        ("🔎", "Где есть бензин сейчас"),
    "/zakrytye-azs":          ("🚫", "Какие АЗС закрылись"),
    "/ocheredi-na-azs":       ("🚗", "Очереди на АЗС"),
    "/draki-na-azs":          ("💢", "Конфликты на АЗС"),
    "/azhiotazh-na-azs":      ("📈", "Ажиотаж на АЗС"),
    "/gde-ai95":              ("⛽", "Где найти АИ-95"),
    "/zapas-benzina-kanistry": ("🛢️", "Запас бензина в канистрах"),
    "/gde-gaz-azs":           ("🔥", "Где заправить газ"),
    "/tankery-ekonomika-rf":  ("💰", "Танкеры и экономика РФ"),
    "/tenevoj-flot":          ("🚢", "Теневой флот — простыми словами"),
    "/krupnejshie-npz-rossii": ("🏭", "Крупнейшие НПЗ России"),
    "/udary-po-energetike-kryma": ("⚡", "Удары по энергетике Крыма"),
    "/zerkalnaya-eskalaciya-energetika": ("⚡", "Зеркальная эскалация по энергетике"),
    "/situaciya-s-benzinom":  ("📊", "Ситуация с бензином"),
    "/skorost-remonta-npz":   ("🔧", "Сколько восстанавливают НПЗ"),
    "/raketnaya-opasnost-belgorod": ("🚀", "Ракетная опасность: Белгород"),
    # кластер складов маркетплейсов — подписи в одном стиле, без сырых «wildberries спб»
    "/udar-po-skladu-ozon":   ("📦", "Удар по складу Ozon"),
    "/sgorel-sklad-wildberries-chto-delat": ("❓", "Сгорел склад Wildberries: что делать"),
    "/udar-sklad-wildberries-peterburg": ("📦", "Удар по складу Wildberries в Петербурге"),
    "/ceny-marketpleysy-posle-udarov": ("💸", "Вырастут ли цены после ударов по складам"),
    "/karta-skladov-wildberries": ("🗺️", "Карта складов Wildberries"),
    # object(/npz/*) — свёрнутый блок «НПЗ по заводам»; подписи = чистое название завода
    # (без служебных слов реестра вида «омский нпз удар»), взято из <title> страниц.
    "/npz/omskij-npz":                  ("🛢️", "Омский НПЗ"),
    "/npz/moskovskij-npz":              ("🛢️", "Московский НПЗ (Капотня)"),
    "/npz/slavneft-yanos":              ("🛢️", "НПЗ ЯНОС (Ярославль)"),
    "/npz/kujbyshevskij-npz":           ("🛢️", "Куйбышевский НПЗ (Самара)"),
    "/npz/ryazanskij-npz":              ("🛢️", "Рязанский НПЗ"),
    "/npz/saratovskij-npz":             ("🛢️", "Саратовский НПЗ"),
    "/npz/taneko-npz":                  ("🛢️", "ТАНЕКО (Нижнекамск)"),
    "/npz/bashneft-ufa":                ("🛢️", "Уфимский НПЗ (Башнефть)"),
    "/npz/taif-nk":                     ("🛢️", "ТАИФ-НК (Нижнекамск)"),
    "/npz/lukojl-norsi":                ("🛢️", "Лукойл-НОРСИ (Кстово)"),
    "/npz/ilskij-npz":                  ("🛢️", "Ильский НПЗ"),
    "/npz/kinef":                       ("🛢️", "Кинеф (Кириши)"),
    "/npz/tuapsinskij-npz":             ("🛢️", "Туапсинский НПЗ"),
    "/npz/syzranskij-npz":              ("🛢️", "Сызранский НПЗ"),
    "/npz/afipskij-npz":                ("🛢️", "Афипский НПЗ"),
    "/npz/angarskij-npz":               ("🛢️", "Ангарский НПЗ"),
    "/npz/astrahanskij-gpz":            ("🛢️", "Астраханский ГПЗ"),
    "/npz/novokujbyshevskij-npz":       ("🛢️", "Новокуйбышевский НПЗ"),
    "/npz/volgogradskij-npz":           ("🛢️", "Волгоградский НПЗ"),
    "/npz/salavat-npz":                 ("🛢️", "Газпром нефтехим Салават"),
    "/npz/antipinskij-npz":             ("🛢️", "Антипинский НПЗ"),
    "/npz/novoshahtinskij-npz":         ("🛢️", "Новошахтинский НПЗ"),
    "/npz/achinskij-npz":               ("🛢️", "Ачинский НПЗ"),
    "/npz/komsomolskij-npz":            ("🛢️", "Комсомольский НПЗ"),
    "/npz/habarovskij-npz":             ("🛢️", "Хабаровский НПЗ"),
    "/npz/uhtinskij-npz":               ("🛢️", "Ухтинский НПЗ"),
    "/npz/marijskij-npz":               ("🛢️", "Марийский НПЗ"),
    "/npz/yajskij-npz":                 ("🛢️", "Яйский НПЗ"),
    "/npz/surgutskij-zsk":              ("🛢️", "Сургутский ЗСК"),
    "/npz/krasnodarskij-npz":           ("🛢️", "Краснодарский НПЗ"),
    "/npz/lukojl-permnefteorgsintez":   ("🛢️", "Лукойл-Пермнефтеоргсинтез"),
    "/npz/orskij-npz":                  ("🛢️", "Орский НПЗ"),
    "/npz/slavyanskij-npz":             ("🛢️", "Славянский НПЗ"),
    "/npz/ns-oil":                      ("🛢️", "NS-Oil (Новоспасское)"),
}

# Карточки хаба /analytics: url -> (заголовок, описание).
# Обложка НЕ прописывается руками: build_hub берёт /assets/analytics-<slug>-generated.png,
# если файл существует (cover_for). Сгенерил кавер через Codex в это имя → карточка сама
# его подхватит; нет файла → карточка без картинки (без битых <img>).
HUB = {
    "/crimea":     ("Дефицит бензина в Крыму", "Ситуация на АЗС Крыма: почему нет топлива, какие заправки работают, цены и ограничения на продажу"),
    "/krasnodar":  ("Дефицит бензина в Краснодаре", "Топливная ситуация в Краснодарском крае: закрытые АЗС, очереди, цены и причины дефицита"),
    "/moskva":     ("Дефицит бензина в Москве", "Очереди на заправках, лимиты по сетям, цены и когда закончится дефицит в столице"),
    "/raketnaya-opasnost-volgograd": ("Ракетная опасность: Волгоград", "Что означают сигналы воздушной тревоги и ракетной опасности в Волгограде и области, чем отличаются, где смотреть обстановку по региону"),
    "/raketnaya-opasnost-ulyanovsk": ("Ракетная опасность: Ульяновск", "Сигналы воздушной тревоги и ракетной опасности в Ульяновске: что означают, что такое отбой, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-kazan":     ("Ракетная опасность: Казань", "Воздушная тревога и ракетная опасность в Казани и Татарстане: разбор сигналов ГО и карта-радар обстановки по региону"),
    "/raketnaya-opasnost-omsk":      ("Ракетная опасность: Омск", "Сигналы воздушной тревоги и ракетной опасности в Омске и области: что означают, что такое отбой, где смотреть обстановку по региону"),
    "/raketnaya-opasnost-cheboksary": ("Ракетная опасность: Чебоксары", "Воздушная тревога и ракетная опасность в Чебоксарах и Чувашии: разбор сигналов ГО и карта-радар обстановки по региону"),
    "/raketnaya-opasnost-moskovskaya-oblast": ("Ракетная опасность: Московская область", "Сигналы воздушной тревоги и ракетной опасности в Московской области: что означают, чем отличаются, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-penza":     ("Ракетная опасность: Пенза", "Воздушная тревога и ракетная опасность в Пензе и области: что означают сигналы ГО, что такое отбой, где смотреть обстановку"),
    "/raketnaya-opasnost-samara":    ("Ракетная опасность: Самара", "Сигналы воздушной тревоги и ракетной опасности в Самаре и области: разбор, отбой и карта-радар обстановки по региону"),
    "/raketnaya-opasnost-sverdlovskaya-oblast": ("Ракетная опасность: Свердловская область", "Сигналы воздушной тревоги и ракетной опасности в Свердловской области: что означают, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-rostovskaya-oblast": ("Ракетная опасность: Ростовская область", "Сигналы воздушной тревоги и ракетной опасности в Ростовской области: что означают, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-kirovskaya-oblast": ("Ракетная опасность: Кировская область", "Сигналы воздушной тревоги и ракетной опасности в Кировской области: что означают, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-tyumenskaya-oblast": ("Ракетная опасность: Тюменская область", "Сигналы воздушной тревоги и ракетной опасности в Тюменской области: что означают, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-ryazanskaya-oblast": ("Ракетная опасность: Рязанская область", "Сигналы воздушной тревоги и ракетной опасности в Рязанской области: что означают, где следить за обстановкой по региону"),
    "/deficit":    ("Почему нет бензина в России", "Причины дефицита топлива: атаки на НПЗ, экспортный отток, логистические сбои. Когда закончится кризис"),
    "/talony":     ("Бензин по талонам", "Где действуют талоны и лимиты, чем отличаются, как получить топливо в Крыму, Москве и регионах"),
    "/benzin-na-trasse": ("Бензин на трассе", "Где заправиться в пути во время дефицита: как найти рабочую АЗС на федеральной трассе, что с наличием АИ-95/92 по маршруту"),
    "/gde-dizel":  ("Где найти дизель", "Наличие дизельного топлива на АЗС во время дефицита: где смотреть ДТ, чем ситуация с дизелем отличается от бензина, очереди и лимиты"),
    "/crisis":     ("Топливный кризис 2026", "Полная хроника кризиса: от первых ударов до дефицита. Региональные последствия и меры правительства"),
    "/attacks":    ("Хроника ударов по НПЗ", "Все атаки БПЛА на нефтеперерабатывающие заводы: даты, масштаб повреждений, текущий статус"),
    "/refineries": ("Список НПЗ России", "Полная база нефтеперерабатывающих заводов: мощность, загрузка, статус после атак, география"),
    "/npz-lukojla": ("НПЗ Лукойла", "Все четыре завода Лукойла в России: мощности, регионы, какие пострадали от ударов БПЛА"),
    "/npz-rosnefti": ("НПЗ Роснефти", "Все 11 заводов Роснефти в России, включая Уфимскую группу Башнефти: мощности, регионы, какие пострадали от ударов БПЛА"),
    "/npz-gazprom-nefti": ("НПЗ Газпром нефти", "Заводы Газпром нефти: Омский НПЗ (крупнейший в России) и Московский НПЗ в Капотне — мощности, регионы, удары БПЛА"),
    "/karta-benzina-krym": ("Карта бензина в Крыму", "Интерактивная карта наличия топлива: 90+ АЗС Крыма, статус сетей АТАН и ТЭС, лимиты, цены и очереди онлайн"),
    "/karta-bpla": ("Карта БПЛА и тревог", "Карта-радар угроз БПЛА и ракет по регионам России: воздушная тревога, ракетная опасность, отбой — онлайн, оценка по OSINT"),
    "/metodologiya": ("Методология оценки данных", "Как карта считает статусы НПЗ и АЗС, откуда берутся данные, как перепроверяются удары и как часто всё обновляется — открытая методология OSINT-агрегации"),
    "/azs-ryadom": ("АЗС рядом со мной", "Как найти ближайшую работающую заправку через геолокацию: бесплатная карта с фильтром «есть топливо» — честная OSINT-оценка по сети и региону, без фейковых статусов колонок"),
    "/volna-dronov": ("Волна дронов сейчас", "Идёт ли сейчас волна повышенной активности БПЛА: сколько городов и регионов затронуто, архив прошлых волн — оценка по открытому OSINT-мониторингу"),
    "/skolko-skladov-wildberries-ozon": ("Сколько складов у Wildberries и Ozon", "Размер складских сетей двух маркетплейсов в России, сколько объектов поражено ударами БПЛА и какая доля площадей выбыла — с картой крупных распределительных центров"),
    "/kakie-sklady-wildberries-ostalis": ("Какие склады Wildberries и Ozon остались", "Полный список складских объектов Wildberries и Ozon без сообщений об ударе: город, регион, оператор и федеральный округ"),
}


def cover_for(url):
    """Обложка карточки хаба (только <img>, не og:image) — по конвенции имени.
    Предпочитаем .webp (конвейер optimize_cover кладёт его рядом с .png), иначе
    .png; ничего нет на диске — карточка без картинки (без битых <img>)."""
    slug = url.strip("/").replace("/", "-")
    base = ROOT / "assets" / f"analytics-{slug}-generated"
    webp = base.with_suffix(".webp")
    if webp.exists():
        return f"/assets/{webp.name}"
    png = base.with_suffix(".png")
    return f"/assets/{png.name}" if png.exists() else None

TOP_URLS   = {u for u, _, _ in TOP + TOP_TAIL}
HIDE_TYPES = set()  # object(/npz/*) больше не скрыт целиком — свой свёрнутый блок меню, см. GROUPS;
                     # из хаба /analytics по-прежнему не льём, см. HUB_EXCLUDE_GROUPS ниже


def load_reg():
    rows = []
    for line in REG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def label_for(url, primary_kw):
    return LABELS.get(url, ("📄", (primary_kw or url).capitalize()))


def pick(rows, pred):
    """Видимые live-страницы группы (по предикату), исключая верхний уровень и /npz/*."""
    return [r for r in rows
            if r.get("status", "live") == "live"
            and pred(r)
            and r["url"] not in TOP_URLS
            and r.get("type") not in HIDE_TYPES]


def short_label(url, primary_kw, title):
    """Подпись внутри свёрнутого блока меню — заголовок группы в тексте не дублируем
    («Ракетная опасность: Волгоград» → «Волгоград»; для заводов префикса и так нет)."""
    return label_for(url, primary_kw)[1].replace(f"{title}: ", "")


HUB_EXCLUDE_GROUPS = {"НПЗ по заводам"}  # объектные страницы заводов не дублируем карточками
                                          # хаба — там уже есть /refineries со списком всех


def ordered_pages(rows):
    """Все видимые live-страницы в порядке групп (плоско, для хаба)."""
    out = []
    for title, pred, _collapse in GROUPS:
        if title in HUB_EXCLUDE_GROUPS:
            continue
        out.extend(pick(rows, pred))
    return out


# ---- 1) news-nav на лендингах (сгруппированная выпадашка) ----
NAV_RE = re.compile(r'<nav class="news-nav">.*?</nav>', re.DOTALL)


def build_menu(rows, current):
    out = []
    for title, pred, collapse in GROUPS:
        picked = pick(rows, pred)
        if not picked:
            continue
        if title in GROUP_SORT_ALPHA:
            picked = sorted(picked, key=lambda r: label_for(r["url"], r.get("primary_kw"))[1])
        if collapse:
            # свёрнутый блок; авто-раскрыт, если открыта одна из его страниц
            summary_emoji, item_emoji = COLLAPSE_EMOJI.get(title, ("🚀", "📍"))
            op = " open" if any(r["url"] == current for r in picked) else ""
            out.append(f'            <details class="nav-drop-sub"{op}>')
            out.append(f'              <summary>{summary_emoji} {title}</summary>')
            for r in picked:
                lab = short_label(r["url"], r.get("primary_kw"), title)
                cur = ' aria-current="page"' if r["url"] == current else ""
                out.append(f'              <a href="{r["url"]}"{cur}>{item_emoji} {lab}</a>')
            out.append('            </details>')
        else:
            out.append(f'            <div class="nav-drop-group">{title}</div>')
            pinned, subs = split_subgroups(title, picked)
            for r in pinned:
                emoji, lab = label_for(r["url"], r.get("primary_kw"))
                cur = ' aria-current="page"' if r["url"] == current else ""
                out.append(f'            <a href="{r["url"]}"{cur}>{emoji} {lab}</a>')
            for emoji, subtitle, items in subs:
                op = " open" if any(r["url"] == current for r in items) else ""
                out.append(f'            <details class="nav-drop-sub"{op}>')
                out.append(f'              <summary>{emoji} {subtitle}</summary>')
                for r in items:
                    e2, lab = label_for(r["url"], r.get("primary_kw"))
                    cur = ' aria-current="page"' if r["url"] == current else ""
                    out.append(f'              <a href="{r["url"]}"{cur}>{e2} {lab}</a>')
                out.append('            </details>')
    # каталог-хаб последним — /analytics достижим, т.к. клик по самому «Аналитика ▾» теперь
    # открывает меню (preventDefault в nav-dropdown.js), а не переходит на хаб.
    out.append('            <a class="nav-drop-all" href="/analytics">📊 Все статьи · каталог →</a>')
    return "\n".join(out)


def build_nav(rows, current):
    def link(url, emoji, lab):
        cur = ' aria-current="page"' if url == current else ""
        return f'        <a href="{url}"{cur}>{emoji} {lab}</a>'
    L = [link(u, e, l) for u, e, l in TOP]
    drop_cur = ' aria-current="page"' if current == "/analytics" else ""
    L += ['        <div class="nav-dropdown" style="position:relative;display:inline-block">',
          f'          <a href="/analytics"{drop_cur} style="color:var(--teal);font-weight:700">📊 Аналитика ▾</a>',
          '          <div class="nav-dropdown-menu">',
          build_menu(rows, current),
          '          </div>',
          '        </div>']
    L += [link(u, e, l) for u, e, l in TOP_TAIL]
    return '<nav class="news-nav">\n' + "\n".join(L) + '\n      </nav>'


# ---- 1a) единая шапка (лого + nav) на news-header-лендингах ----
# build-nav владеет всем <header class="news-header">, а не только внутренним <nav>:
# логотип больше не копируется руками (был разнобой — 86 страниц вели логотипом на /news,
# 4 на /). radar.html (topbar) и index.html (tab-бар) — свои шапки, их не трогаем (у них
# управляется только внутренний nav, ниже в main()).
HEADER_RE = re.compile(r'<header class="news-header">.*?</header>', re.DOTALL)
LOGO_HTML = ('      <a href="/" class="news-logo" title="На карту">\n'
             '        <span class="news-logo-icon">⛽</span>\n'
             '        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>\n'
             '      </a>')


SEARCH_BTN = ('<button type="button" class="nav-search-btn" id="searchOpenBtn" '
              'title="Поиск по сайту" aria-label="Поиск по сайту">🔍</button>')


def build_header(rows, current):
    return ('<header class="news-header">\n'
            '    <div class="news-header-inner">\n'
            + LOGO_HTML + '\n'
            '      ' + build_nav(rows, current) + '\n'
            '      ' + SEARCH_BTN + '\n'
            '    </div>\n'
            '  </header>')


# ---- 1b) единый брендированный футер на SEO-лендингах + /analytics ----
FOOTER_HTML = ('  <footer class="news-footer">\n'
               '    <div class="news-footer-inner">\n'
               '      <p>Топливный фронт РФ · <a href="/">🗺️ Карта НПЗ</a> · OSINT-дашборд · '
               '<span class="mono">npz-tactical-map.vercel.app</span></p>\n'
               '      <p class="footer-disc">Не является официальной информацией. Данные из открытых источников.</p>\n'
               '    </div>\n'
               '  </footer>\n')
FOOTER_RE = re.compile(r'[ \t]*<footer class="news-footer">.*?</footer>\n?', re.DOTALL)
FOOTER_SKIP = {"radar.html"}  # тикер живых сводок, не SEO-футер — не трогаем


def apply_footer(html, fname):
    if fname in FOOTER_SKIP:
        return html
    if FOOTER_RE.search(html):
        return FOOTER_RE.sub(FOOTER_HTML, html, count=1)
    if "</main>" in html:
        return html.replace("</main>", "</main>\n\n" + FOOTER_HTML, 1)
    return html


# ---- 2) дропдаун на ГЛАВНОЙ (index.html) — сгруппирован по маркерам ----
# Маркеры (а не regex по <div>) потому что группы содержат вложенные </div>/<details>.
INDEX_MENU_RE = re.compile(r'(<!-- INDEX-MENU:START -->)(.*?)(<!-- INDEX-MENU:END -->)', re.DOTALL)


def build_index_menu(rows):
    lines = ["\n"]
    for title, pred, collapse in GROUPS:
        picked = pick(rows, pred)
        if not picked:
            continue
        if title in GROUP_SORT_ALPHA:
            picked = sorted(picked, key=lambda r: label_for(r["url"], r.get("primary_kw"))[1])
        if collapse:
            summary_emoji, item_emoji = COLLAPSE_EMOJI.get(title, ("🚀", "📍"))
            lines.append('            <details class="tdm-sub">\n')
            lines.append(f'              <summary>{summary_emoji} {title}</summary>\n')
            for r in picked:
                lab = short_label(r["url"], r.get("primary_kw"), title)
                lines.append(f'              <a href="{r["url"]}">{item_emoji} {lab}</a>\n')
            lines.append('            </details>\n')
        else:
            lines.append(f'            <div class="tdm-group">{title}</div>\n')
            pinned, subs = split_subgroups(title, picked)
            for r in pinned:
                emoji, lab = label_for(r["url"], r.get("primary_kw"))
                lines.append(f'            <a href="{r["url"]}">{emoji} {lab}</a>\n')
            for emoji, subtitle, items in subs:
                lines.append('            <details class="tdm-sub">\n')
                lines.append(f'              <summary>{emoji} {subtitle}</summary>\n')
                for r in items:
                    e2, lab = label_for(r["url"], r.get("primary_kw"))
                    lines.append(f'              <a href="{r["url"]}">{e2} {lab}</a>\n')
                lines.append('            </details>\n')
    lines.append('            <a class="tdm-all" href="/analytics">📊 Все статьи · каталог →</a>\n')
    return "".join(lines) + "          "


# ---- 2c) мобильный drawer в radar.html — «Аналитика» (плоско + свёрнутая ракетная, по маркерам) ----
DRAWER_RE = re.compile(r'(<!-- DRAWER-ANALYTICS:START -->)(.*?)(<!-- DRAWER-ANALYTICS:END -->)', re.DOTALL)
DRAWER_SKIP = {"/help"}  # /help закреплён в группе «Разделы» drawer'а — не дублируем в «Аналитике»


def build_drawer_analytics(rows):
    lines = ["\n"]
    for title, pred, collapse in GROUPS:
        picked = [r for r in pick(rows, pred) if r["url"] not in DRAWER_SKIP]
        if not picked:
            continue
        if title in GROUP_SORT_ALPHA:
            picked = sorted(picked, key=lambda r: label_for(r["url"], r.get("primary_kw"))[1])
        if collapse:
            summary_emoji, item_emoji = COLLAPSE_EMOJI.get(title, ("🚀", "📍"))
            lines.append('      <details class="ndp-sub">\n')
            lines.append(f'        <summary class="ndp-item">{summary_emoji} {title}</summary>\n')
            for r in picked:
                lab = short_label(r["url"], r.get("primary_kw"), title)
                lines.append(f'        <a class="ndp-item ndp-subitem" href="{r["url"]}">{item_emoji} {lab}</a>\n')
            lines.append('      </details>\n')
        else:
            pinned, subs = split_subgroups(title, picked)
            for r in pinned:
                emoji, lab = label_for(r["url"], r.get("primary_kw"))
                lines.append(f'      <a class="ndp-item" href="{r["url"]}">{emoji} {lab}</a>\n')
            for emoji, subtitle, items in subs:
                lines.append('      <details class="ndp-sub">\n')
                lines.append(f'        <summary class="ndp-item">{emoji} {subtitle}</summary>\n')
                for r in items:
                    e2, lab = label_for(r["url"], r.get("primary_kw"))
                    lines.append(f'        <a class="ndp-item ndp-subitem" href="{r["url"]}">{e2} {lab}</a>\n')
                lines.append('      </details>\n')
    return "".join(lines) + "      "


# ---- 2b) «Свежее»-чип на ГЛАВНОЙ (в status-strip → .ss-nav) ----
FRESH_RE  = re.compile(r'<!-- FRESH:START -->.*?<!-- FRESH:END -->', re.DOTALL)
SSNAV_RE  = re.compile(r'(<nav class="ss-nav"[^>]*>)')

# 🆕-чип светит ТОЛЬКО статьи, фичи не светим (решение 15.07).
# reference нужен ради разборов (/udary-azovskoe-more, /udary-po-tankeram) — но в нём же лежат
# фича-страница и служебные разделы, тип их не различает → отсекаем поимённо ниже.
# tool = ВСЕ карты (/karta-bpla, /radar, /karta-azs, /gde-est-benzin…) = фичи → не светим.
# object = страницы НПЗ → не статьи.
# Свежесть = ПОРЯДОК СТРОК в реестре (дат в нём нет), TOP_URLS отсеиваются ниже.
FRESH_TYPES = {"region", "explainer", "forecast", "reference"}
FRESH_EXCLUDE = {"/volna-dronov", "/help", "/metodologiya"}  # лежат как reference, но не статьи


def newest_page(rows):
    # «новейшая» = последняя добавленная в реестр live-страница из контентных типов
    cands = [r for r in rows if r.get("status", "live") == "live"
             and r.get("type") in FRESH_TYPES
             and r["url"] not in TOP_URLS
             and r["url"] not in FRESH_EXCLUDE]
    return cands[-1] if cands else None

def build_fresh_chip(rows):
    r = newest_page(rows)
    if not r:
        return "<!-- FRESH:START --><!-- FRESH:END -->"
    _, lab = label_for(r["url"], r.get("primary_kw"))
    return ('<!-- FRESH:START --><a class="ss-src ss-fresh" href="%s" '
            'style="background:var(--teal,#12a594);color:#fff;font-weight:700;border-radius:8px">'
            '🆕 %s →</a><!-- FRESH:END -->') % (r["url"], lab)


# ---- 3) каталог-хаб /analytics (маркеры) ----
HUB_RE = re.compile(r'(<!-- ANALYTICS-CARDS:START -->)(.*?)(<!-- ANALYTICS-CARDS:END -->)', re.DOTALL)


def build_hub(rows):
    cards = ["\n"]
    for r in ordered_pages(rows):
        url = r["url"]
        title, desc = HUB.get(url, (label_for(url, r.get("primary_kw"))[1], r.get("primary_kw", "")))
        cover = cover_for(url)  # обложка по конвенции имени, только если файл есть на диске
        # ponytail: alt = заголовок карточки (осмысленный, не decorative) — было alt="" на всех обложках
        img = f'\n        <img class="card-cover" src="{cover}" alt="{title}" loading="lazy">' if cover else ""
        cards.append(
            f'      <a href="{url}" class="analytics-card">{img}\n'
            f'        <div class="card-body">\n'
            f'          <h2>{title}</h2>\n'
            f'          <p>{desc}</p>\n'
            f'          <div class="card-meta">→ Читать</div>\n'
            f'        </div>\n'
            f'      </a>\n\n'
        )
    return "".join(cards) + "      "


# ---- 4) cache-busting ассетов в index.html ----
# Лендинги штампует gen-news.py (?v=md5[:8]); index.html их не касался → у вернувшихся
# посетителей висел кэш styles.css/app.js и правки шапки/меню не доезжали. Штампуем тут,
# на каждом regenerate — само-заживает: правка styles.css → новый хэш → браузер перекачает.
# опциональный ведущий слэш: index.html линкует "styles.css", лендинги — "/styles.css".
ASSET_RE = re.compile(r'(href|src)="(/?)(styles\.css|news\.css|app\.js|nav-dropdown\.js|search\.css|search\.js|vpn-nudge\.js)(\?v=[0-9a-f]+)?"')


# ---- 4a) единый инжект поиска (search.css/search.js) в <head> на всех страницах ----
# build-nav — единственный владелец: добавил страницу → поиск на ней есть автоматически.
# Идемпотентно (если /search.js уже линкован — не трогаем; stamp_assets потом навесит ?v).
SEARCH_HEAD = ('  <link rel="stylesheet" href="/search.css">\n'
               '  <script defer src="/search.js"></script>\n')


def ensure_search_assets(html):
    if '/search.js' in html:
        return html
    if '</head>' in html:
        return html.replace('</head>', SEARCH_HEAD + '</head>', 1)
    return html


# ---- 4b) единый инжект VPN-баннера (vpn-nudge.js) на всех статических страницах ----
# build-nav — единственный владелец: добавил страницу → баннер на ней есть автоматически и
# переживает любой regenerate (раньше баннер вставляли вручную → рутины его затирали при
# пересборке news/SEO). Идемпотентно. Карту (app.js) НЕ трогаем — там баннер уже в попапах.
VPN_SCRIPT_TAG = '  <script defer src="/vpn-nudge.js"></script>\n'
# app.js ЗАГРУЖЕН как скрипт (карта) — не по упоминанию в комменте (radar пишет «app.js initMobile»).
APP_JS_LOADED = re.compile(r'src="[^"]*app\.js')


def ensure_vpn_asset(html):
    if 'vpn-nudge.js' in html or APP_JS_LOADED.search(html):
        return html
    if '</body>' in html:
        return html.replace('</body>', VPN_SCRIPT_TAG + '</body>', 1)
    return html


def stamp_assets(html):
    def repl(m):
        attr, slash, fname = m.group(1), m.group(2), m.group(3)
        p = ROOT / fname
        if not p.exists():
            return m.group(0)
        h = hashlib.md5(p.read_bytes()).hexdigest()[:8]
        return f'{attr}="{slash}{fname}?v={h}"'
    return ASSET_RE.sub(repl, html)


# ---- 5) единая клик-выпадашка «Аналитика» на лендингах ----
# Инлайн-JS дропдауна дрейфовал по 30+ страницам (4 разных копии), а сводки/npz были вовсе
# без JS (hover-only → не открыть на тач-планшетах >768). Теперь один shared /nav-dropdown.js
# (клик-фиксация .open + клик-вне/Esc, зеркалит index.html). Здесь вырезаем СТАРЫЕ инлайн-
# конструкции дропдауна (тему/SW/прочее в том же <script> НЕ трогаем) и линкуем shared-скрипт.
# ponytail: регэкспы бьют по 4 известным формам инлайна; генераторы их больше не эмитят, 5-я не заведётся.
DROP_FOREACH_RE = re.compile(
    r"[ \t]*(?://[^\n]*\n[ \t]*)?document\.querySelectorAll\((['\"])\.nav-dropdown > a\1\)"
    r"\.forEach\(.*?\}\);\s*\}\);\n?",
    re.DOTALL)
DROP_OUTSIDE_RE = re.compile(
    r"[ \t]*(?://[^\n]*\n[ \t]*)?document\.addEventListener\((['\"])click\1,\s*function\(e\)\s*\{\s*"
    r"if\s*\(!e\.target\.closest\((['\"])\.nav-dropdown\2\)\).*?\}\);\n?",
    re.DOTALL)
DROP_SCRIPT_TAG = '  <script defer src="/nav-dropdown.js"></script>\n'


def wire_dropdown(html):
    """Срезать старый инлайн-JS дропдауна и вставить shared /nav-dropdown.js перед </body>."""
    html = DROP_FOREACH_RE.sub("", html)
    html = DROP_OUTSIDE_RE.sub("", html)
    if "/nav-dropdown.js" not in html and "</body>" in html:
        html = html.replace("</body>", DROP_SCRIPT_TAG + "</body>", 1)
    return html


# ---- 5a) кнопка «АНАЛИТИКА ▾» на ГЛАВНОЙ (index.html, .tab-dropdown) ----
# index.html — свой topbar (не news-header), инлайн-скрипт клика тут не заменён на shared
# /nav-dropdown.js исторически; но по факту это тот же паттерн клик-фиксации .open. Он
# генерируется здесь (не руками в index.html), чтобы не разъезжаться со shared-версией:
# десктоп (реальная мышь, hover работает) — клик уходит на /analytics; тач — preventDefault
# + .open, ровно как в nav-dropdown.js. Зеркало правится синхронно с nav-dropdown.js выше.
TAB_DROPDOWN_JS_RE = re.compile(
    r'<script>\n\s*// АНАЛИТИКА:.*?</script>', re.DOTALL)
TAB_DROPDOWN_JS = '''<script>
    // АНАЛИТИКА: десктоп (реальная мышь, hover работает) — клик по «АНАЛИТИКА ▾» ведёт
    // на /analytics, меню раскрывается по наведению (CSS :hover, см. styles.css). На тач
    // hover ненадёжен — там клик закрепляет меню (класс .open), закрытие — клик вне / Esc.
    // /analytics всё равно достижим пунктом «Все статьи · каталог →» внутри меню.
    // Зеркалит nav-dropdown.js (там та же логика для лендингов) — правь синхронно.
    document.querySelectorAll('.tab-dropdown > .tab-link-inner').forEach(a => {
      a.addEventListener('click', function(e) {
        if (window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
        e.preventDefault();
        this.closest('.tab-dropdown').classList.toggle('open');
      });
    });
    const closeDrops = () => document.querySelectorAll('.tab-dropdown.open')
      .forEach(d => d.classList.remove('open'));
    document.addEventListener('click', e => { if (!e.target.closest('.tab-dropdown')) closeDrops(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrops(); });
  </script>'''


def wire_tab_dropdown(html):
    return TAB_DROPDOWN_JS_RE.sub(TAB_DROPDOWN_JS, html, count=1)


def main():
    rows = load_reg()
    changed = 0
    # «Свежее»-чип считаем один раз и применяем ко ВСЕМ страницам с маркерами (не только к
    # index): у karta-azs / karta-azs-lab свои FRESH-маркеры, и раньше их не обновлял никто —
    # чип там застревал навсегда.
    fresh_chip = build_fresh_chip(rows)

    # 1) news-nav + футер на всех лендингах, у которых он есть (авто-обнаружение —
    # не забыть добавить в список больше нельзя); news/*.html — архив сводок,
    # volna-dronov/*.html — вечные снимки волн (agents/gen-wave.py), тот же паттерн.
    landings = sorted(list(ROOT.glob("*.html")) + list(ROOT.glob("npz/*.html"))
                       + list(ROOT.glob("news/*.html")) + list(ROOT.glob("volna-dronov/*.html")))
    for f in landings:
        if f.name == "index.html":
            continue
        html = f.read_text(encoding="utf-8")
        # обрабатываем страницу, если есть ЛЮБОЙ маркер: news-header (build-nav наполнит
        # шапку целиком — так новая страница = пустой <header class="news-header"></header>)
        # или news-nav без header (radar — только внутренний nav).
        if '<nav class="news-nav">' not in html and '<header class="news-header">' not in html:
            continue
        current = "/" + str(f.relative_to(ROOT))[:-5]
        # news-header-лендинги → build-nav владеет всей шапкой (лого + nav);
        # radar (topbar, без news-header) → только внутренний nav, как раньше.
        if '<header class="news-header">' in html:
            new = HEADER_RE.sub(build_header(rows, current), html, count=1)
        else:
            new = NAV_RE.sub(build_nav(rows, current), html, count=1)
        new = apply_footer(new, f.name)
        new = DRAWER_RE.sub(lambda m: m.group(1) + build_drawer_analytics(rows) + m.group(3), new, count=1)
        new = wire_dropdown(new)  # срезать старый инлайн-JS дропдауна + линковать shared /nav-dropdown.js
        new = ensure_search_assets(new)  # search.css/search.js в <head> (поиск на всех страницах)
        new = ensure_vpn_asset(new)  # vpn-nudge.js перед </body> (VPN-баннер на всех статических страницах)
        new = stamp_assets(new)  # освежить ?v на styles.css/news.css/nav-dropdown.js — иначе правка не доедет до вернувшихся
        if new != html:
            f.write_text(new, encoding="utf-8"); changed += 1; print("nav/footer updated", f.relative_to(ROOT))

    # 1b) «Свежее»-чип на НЕ-index страницах с маркерами. Отдельным проходом, потому что цикл
    # выше пропускает страницы без news-nav/news-header (karta-azs* — карты, у них topbar),
    # а FRESH-маркеры у них есть → чип там застревал навсегда (был /gde-est-benzin).
    for f in landings:
        if f.name == "index.html":
            continue
        html = f.read_text(encoding="utf-8")
        if not FRESH_RE.search(html):
            continue
        new = FRESH_RE.sub(fresh_chip, html, count=1)
        # эти же страницы цикл выше не штампует → их ?v протухал молча (karta-azs тянула
        # старый vpn-nudge). Штампуем здесь, иначе правки ассетов до них не доезжают.
        new = stamp_assets(new)
        if new != html:
            f.write_text(new, encoding="utf-8"); changed += 1; print("fresh chip + asset ver updated", f.relative_to(ROOT))

    # 2) главная — дропдаун (⚠️ фронтенд-ядро, коммит под ALLOW_FRONTEND_RELEASE=1)
    idx = ROOT / "index.html"
    if idx.exists():
        html = idx.read_text(encoding="utf-8")
        new, n = INDEX_MENU_RE.subn(lambda m: m.group(1) + build_index_menu(rows) + m.group(3), html, count=1)
        if n == 0:
            print("!! no tab-dropdown-menu in index.html")
        # «Свежее»-чип: обновить между маркерами, либо вставить первым в .ss-nav
        chip = fresh_chip
        if FRESH_RE.search(new):
            new = FRESH_RE.sub(chip, new, count=1)
        elif SSNAV_RE.search(new):
            new = SSNAV_RE.sub(lambda m: m.group(1) + "\n        " + chip, new, count=1)
        else:
            print("!! no .ss-nav in index.html (chip skipped)")
        # мобильный drawer «Аналитика» — из того же реестра (был hand-maintained → дрейфовал)
        new = DRAWER_RE.sub(lambda m: m.group(1) + build_drawer_analytics(rows) + m.group(3), new, count=1)
        new = wire_tab_dropdown(new)  # клик по «АНАЛИТИКА ▾»: десктоп → /analytics, тач → .open
        new = ensure_search_assets(new)  # search.css/search.js в <head>
        new = stamp_assets(new)  # ?v=<хэш> на styles.css/app.js — иначе кэш прячет правки шапки
        if new != html:
            idx.write_text(new, encoding="utf-8"); changed += 1; print("index.html dropdown + drawer + fresh chip + asset ver updated")

    # 3) хаб /analytics — сетка карточек (по маркерам)
    hub = ROOT / "analytics.html"
    if hub.exists():
        html = hub.read_text(encoding="utf-8")
        new, n = HUB_RE.subn(lambda m: m.group(1) + build_hub(rows) + m.group(3), html, count=1)
        if n == 0:
            print("!! no ANALYTICS-CARDS markers in analytics.html")
        elif new != html:
            hub.write_text(new, encoding="utf-8"); changed += 1; print("analytics.html hub updated")

    print(f"done, {changed} files changed")


if __name__ == "__main__":
    main()
