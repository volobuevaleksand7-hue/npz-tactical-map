#!/usr/bin/env python3
"""
radar_publish.py — Двухуровневая система оповещений «Молния» / «Обычные новости».

TIER 1 (МОЛНИЯ / Breaking):
  - Автопубликация в канал @NPZmap И всем активным подписчикам бота
  - Триггеры: удар по НПЗ (status down/partial), атака 100+ БПЛА,
    стратегические инфраструктурные объекты
  - Формат: "МОЛНИЯ | [headline]\n[details]\nКарта: npz-tactical-map.vercel.app"

TIER 2 (Обычные):
  - Отправка в текущий чат (609952529) с inline-кнопкой «Выложить в группу»
  - По нажатию — пересылка в @NPZmap

Использование:
  # Прямой вызов из кода:
  from radar_publish import classify_news, publish_major, publish_with_button, handle_callback

  # CLI (тест / дайджест):
  python3 radar_publish.py --classify '{"target":"Омский НПЗ","type":"drone","count":150}'
  python3 radar_publish.py --major "МОЛНИЯ | Тестовый алерт\nДетали..."
  python3 radar_publish.py --regular "Обычное обновление карты"
  python3 radar_publish.py --dry-run --major "МОЛНИЯ | Тест"
  python3 radar_publish.py --dry-run --regular "Обычное обновление"

Файл: hermes/bot/radar_publish.py
"""
import json, os, sys, time, urllib.request, urllib.parse, datetime, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
import day_state as DS

# ─── Конфиг ───────────────────────────────────────────────────────────────────
HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
TOKEN = open(os.path.join(BOT_DIR, "token")).read().strip()
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
API = "https://api.telegram.org/bot" + TOKEN
SITE = "https://npz-tactical-map.vercel.app"

CHANNEL_CHAT_ID = "-1004491068477"   # @NPZmap
ADMIN_CHAT_ID = "609952529"         # текущий чат для tier-2

# ─── Константы классификации ─────────────────────────────────────────────────
# Слова в target/title, обозначающие удар по НПЗ/нефтепереработке
NPZ_KEYWORDS = [
    "нпз", "нефтеперерабатывающ", "нефтебаз", "насосн", "депо",
    "перегон", "АВТ", "ЕЛОУ", "КУ-1", "АТ", "АТМ", "crude",
    "нефтепереработк", "бензин", "дизель", "топлив",
]

# Стратегические объекты (военная инфраструктура, энергетика)
STRATEGIC_KEYWORDS = [
    "ракетн", "ракетно-космич", "ВПК", "оборонн", "завод",
    "авиазавод", "трубопровод", "газопровод", "ТЭЦ", "ГРЭС",
    "генерац", "электростанц", "атомн", "АЭС", "морской порт",
    "морского базир", "авиабаз", "военный аэродром",
    "Су-57", "Су-35", "Т-14", "БМП", "Т-90",
    # 22.07: крупная гражданская логистика. Удары по складам Wildberries в
    # Краснодаре и Невинномысске (10 и 5 пострадавших) не подходили ни под один
    # критерий выше — «не топливо, не оборонка» — и не стали бы молнией даже
    # после того, как их руками добавили на карту.
    "логистическ", "распределительн", "склад", "маркетплейс",
    "wildberries", "ozon", "элеватор", "железнодорожн", "аэропорт",
]

# Ключевые слова, исключающие «мажорность»
MINOR_KEYWORDS = [
    "перехват", "сбит", "отбит", "отражён", "ПВО отразила",
    "минорн", "малая мощность", "незначительн",
]


def jload(path, default=None):
    """Загрузка JSON из файла."""
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def api_call(method, **params):
    """Вызов Telegram Bot API."""
    data = urllib.parse.urlencode(params).encode()
    try:
        r = urllib.request.urlopen(API + "/" + method, data=data, timeout=30)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"error_code": e.code}
        return body
    except Exception as e:
        return {"ok": False, "description": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# КЛАССИФИКАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def classify_news(strike_data):
    """
    Классифицировать событие как "major" (tier 1 — МОЛНИЯ) или "regular" (tier 2).

    strike_data — dict с полями: target, title, detail, type, count, city,
                  region и любые другие из strikes.json

    Возвращает: ("major", {"headline": ..., "reason": ...}) или
                ("regular", {"headline": ..., "reason": ...})
    """
    target = str(strike_data.get("target", "")).lower()
    title = str(strike_data.get("title", "")).lower()
    detail = str(strike_data.get("detail", "")).lower()
    hit_type = str(strike_data.get("type", "")).lower()
    count = strike_data.get("count") or 0
    city = str(strike_data.get("city", "")).lower()
    region = str(strike_data.get("region", "")).lower()
    confidence = str(strike_data.get("confidence", "")).lower()

    searchable = f"{target} {title} {detail} {city} {region}"

    reasons = []

    # ── Проверка 1: Удар по НПЗ / нефтеперерабатывающему объекту ──
    npz_hit = any(kw in searchable for kw in NPZ_KEYWORDS)
    if npz_hit:
        reasons.append("НПЗ/нефтеперерабатывающий объект")

    # ── Проверка 2: Массовая атака (100+ БПЛА/ракет) ──
    large_scale = False
    if isinstance(count, (int, float)) and count >= 100:
        large_scale = True
        reasons.append(f"Массовая атака ({int(count)} БПЛА/ракет)")
    # Эвристика: если тип «drone» и count неизвестен, но город в списке крупных
    # при этом есть ключевые слова типа «волна», « группировк», «массов»
    wave_keywords = ["волна", " группировк", "массов", "массирован", "рекорд"]
    if not count and any(kw in searchable for kw in wave_keywords) and hit_type in ("drone", "both", "missile"):
        # Не автоматически major — нужно подтверждение по другим признакам
        if npz_hit:
            reasons.append("Массовая атака (подозрение — волна)")
            large_scale = True

    # ── Проверка 3: Стратегическая инфраструктура ──
    strategic = any(kw in searchable for kw in STRATEGIC_KEYWORDS)
    if strategic:
        reasons.append("Стратегическая инфраструктура")

    # ── Проверка 4: Статус НПЗ down/partial (если передан в данных) ──
    status = str(strike_data.get("status", "")).lower()
    if status in ("down", "partial"):
        reasons.append(f"НПЗ статус: {status}")
        npz_hit = True

    # ── Проверка 5: Крупный город-миллионник ──
    major_cities = [
        "москва", "петербург", "санкт-петербург", "екатеринбург",
        "казань", "нижний новгород", "новосибирск", "омск", "самара",
        "челябинск", "уфа", "ростов", "красноярск", "волжск",
        "пермь", "волгоград", "краснодар",
    ]
    city_major = any(mc in city for mc in major_cities)
    if city_major and (npz_hit or strategic):
        reasons.append(f"Крупный город ({strike_data.get('city', '')})")

    # ── Проверка 6: Пострадавшие ──
    # Объективный признак крупного удара, не зависящий от типа объекта: если есть
    # раненые или погибшие, это молния независимо от того, что именно поражено.
    casualties = strike_data.get("casualties") or 0
    try:
        casualties = int(casualties)
    except (TypeError, ValueError):
        casualties = 0
    if casualties > 0:
        reasons.append("Пострадавшие: %d" % casualties)

    # ── Проверка 7: Исключения — сбитые дроны, малые объекты ──
    is_minor = any(kw in searchable for kw in MINOR_KEYWORDS)
    if is_minor and not npz_hit and not casualties:
        return ("regular", {
            "headline": strike_data.get("title", strike_data.get("target", "")),
            "reason": "minor/marginal event",
        })

    # ── Решение ──
    if reasons:
        headline = strike_data.get("title", strike_data.get("target", ""))
        return ("major", {
            "headline": headline,
            "reason": "; ".join(reasons),
            "npz_hit": npz_hit,
            "large_scale": large_scale,
            "strategic": strategic,
        })
    else:
        headline = strike_data.get("title", strike_data.get("target", ""))
        return ("regular", {
            "headline": headline,
            "reason": "routine / no major triggers matched",
        })


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 1 — МОЛНИЯ (autonomous publish)
# ═══════════════════════════════════════════════════════════════════════════════

def _format_molniya(text):
    """LEGACY: старое текстовое форматирование МОЛНИИ (для CLI --major с сырым текстом).
    Публикация из strikes.json теперь идёт через strike_to_molniya_event() + render_molniya()."""
    text = text.strip()
    if not text.startswith("МОЛНИЯ"):
        text = f"МОЛНИЯ | {text}"
    if SITE not in text:
        text = f"{text}\n\n🗺 Карта: {SITE}"
    return text


def _clip_words(text, limit):
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:—-") + "…"


def _short_why(strike):
    """Короткая редакционная строка «что это и почему важно» — из detail/target
    самого события, НЕ из внутренних причин классификатора (те — для логов,
    не для читателя). Предпочитаем часть ПОСЛЕ первого «—» (обычно там и есть
    пояснение), иначе — первую скобочную вставку, иначе — первое предложение detail."""
    target_full = str(strike.get("target") or "")
    if "—" in target_full:
        after_dash = target_full.split("—", 1)[1].strip()
        if after_dash:
            return _clip_words(after_dash, 120)
    if "(" in target_full and ")" in target_full:
        inside = target_full.split("(", 1)[1].split(")", 1)[0].strip()
        if inside:
            return _clip_words(inside, 120)
    detail = str(strike.get("detail", "")).strip()
    if detail:
        import re as _re
        parts = _re.split(r"(?<=[.!?])\s", detail, maxsplit=1)
        return _clip_words(parts[0] if parts else detail, 120)
    return ""


def strike_to_molniya_event(strike, reason=""):
    """Конвертирует запись из strikes.json в event-payload для render.render_molniya().
    `reason` (внутренняя причина TIER1-классификации) НЕ идёт в текст поста —
    используется только для логов пайплайна."""
    city = strike.get("city", "")
    region = strike.get("region", "")
    target = str(strike.get("target") or strike.get("title") or "").split("(")[0].strip()
    confidence = "confirmed" if strike.get("confidence") == "confirmed" else "reported"
    sources = []
    if strike.get("source_url"):
        # render_molniya печатает sources как текстовые метки (не голые URL) —
        # передаём короткую метку "источник карты", ссылка живёт в самом посте
        # через blockquote/detail, а не как голый URL, чтобы пройти preflight.
        sources.append("данные карты")
    context = str(strike.get("detail", ""))[:180]
    return {
        "headline": strike.get("title") or ("%s: %s" % (city, target)),
        "city": city,
        "region": region,
        "target": target or "инфраструктура",
        "why": _short_why(strike),
        "confidence": confidence,
        "sources": sources,
        "context": context,
        "url": SITE,
    }


def molniya_dedup_key(strike):
    date_iso = str(strike.get("date", ""))[:10] or DS.today_iso()
    return DS.make_key(date_iso, "molniya", strike.get("city", ""),
                        strike.get("target") or strike.get("title", ""))


def _get_active_subscribers():
    """Получить список chat_id активных подписчиков."""
    subs_doc = jload(SUBS_PATH, {"subscribers": {}})
    subscribers = subs_doc.get("subscribers", {})
    return [
        cid for cid, info in subscribers.items()
        if info.get("status") == "active"
    ]


def publish_major(text, dry_run=False):
    """
    ТIER 1: Отправить МОЛНИЮ в канал @NPZmap + всем активным подписчикам.

    text — текст оповещения (будет отформатирован)
    dry_run — если True, только печатает что отправил бы
    Возвращает: {"channel_ok": bool, "subscribers_sent": int, "errors": []}
    """
    formatted = _format_molniya(text)
    errors = []
    result = {"channel_ok": False, "subscribers_sent": 0, "errors": errors}

    if dry_run:
        print(f"\n{'='*60}")
        print(f"[DRY-RUN] TIER 1 — МОЛНИЯ")
        print(f"{'='*60}")
        print(f"Форматированный текст:\n{formatted}")
        print(f"\nПолучатели:")
        print(f"  Канал: {CHANNEL_CHAT_ID} (@NPZmap)")
        subscribers = _get_active_subscribers()
        print(f"  Подписчики ({len(subscribers)}): {subscribers}")
        print(f"{'='*60}\n")
        result["channel_ok"] = True
        result["subscribers_sent"] = len(subscribers)
        return result

    # 1) В канал @NPZmap
    try:
        resp = api_call(
            "sendMessage",
            chat_id=CHANNEL_CHAT_ID,
            text=formatted,
            parse_mode="HTML",
            disable_web_page_preview="true",
        )
        result["channel_ok"] = resp.get("ok", False)
        if not result["channel_ok"]:
            errors.append(f"channel: {resp.get('description', 'unknown error')}")
    except Exception as e:
        errors.append(f"channel exception: {e}")

    # 2) Всем активным подписчикам
    subscribers = _get_active_subscribers()
    sent = 0
    for cid in subscribers:
        time.sleep(0.1)  # rate-limit guard
        try:
            resp = api_call(
                "sendMessage",
                chat_id=cid,
                text=formatted,
                parse_mode="HTML",
                disable_web_page_preview="true",
            )
            if resp.get("ok"):
                sent += 1
            else:
                code = resp.get("error_code", 0)
                if code in (403, 400):
                    # Помечаем как заблокированного
                    _mark_blocked(cid)
                errors.append(f"subscriber {cid}: {resp.get('description', '')}")
        except Exception as e:
            errors.append(f"subscriber {cid} exception: {e}")

    result["subscribers_sent"] = sent
    return result


def publish_strike_molniya(strike, reason="", dry_run=False):
    """TIER 1 (единый прод-путь, редполитика v2): рендерит МОЛНИЮ через render.py,
    проверяет единый дедуп (day_state.published_keys), публикует в канал +
    подписчикам, регистрирует ключ и molniya_ref (чтобы сводка сослалась на
    неё вместо дублирования). Повтор по тому же объекту в тот же день —
    редактирование существующей молнии апдейт-строкой, не новая публикация.
    Возвращает {"channel_ok", "subscribers_sent", "errors", "skipped_duplicate", "key"}.
    """
    key = molniya_dedup_key(strike)
    state = DS.ensure_today(DS.load_state())

    if DS.is_published(state, key) and not dry_run:
        return {"channel_ok": False, "subscribers_sent": 0, "errors": [],
                "skipped_duplicate": True, "key": key}

    event = strike_to_molniya_event(strike, reason=reason)
    text = R.render_molniya(event)
    ok_pf, reason_pf = R.preflight(text, R.MOLNIYA_MAX)
    if not ok_pf:
        return {"channel_ok": False, "subscribers_sent": 0,
                "errors": ["preflight: %s" % reason_pf], "skipped_duplicate": False, "key": key}

    if dry_run:
        print(f"\n{'='*60}\n[DRY-RUN] TIER 1 — МОЛНИЯ (единый рендер)\n{'='*60}")
        print(text)
        subscribers = _get_active_subscribers()
        print(f"\nКанал: {CHANNEL_CHAT_ID} (@NPZmap)\nПодписчики ({len(subscribers)}): {subscribers}")
        print(f"{'='*60}\n")
        return {"channel_ok": True, "subscribers_sent": len(subscribers), "errors": [],
                "skipped_duplicate": False, "key": key}

    errors = []
    channel_ok = False
    channel_message_id = None
    try:
        resp = api_call("sendMessage", chat_id=CHANNEL_CHAT_ID, text=text,
                         parse_mode="HTML", disable_web_page_preview="true")
        channel_ok = resp.get("ok", False)
        channel_message_id = (resp.get("result") or {}).get("message_id")
        if not channel_ok:
            errors.append(f"channel: {resp.get('description', 'unknown error')}")
    except Exception as e:
        errors.append(f"channel exception: {e}")

    subscribers = _get_active_subscribers()
    sent = 0
    for cid in subscribers:
        time.sleep(0.1)
        try:
            resp = api_call("sendMessage", chat_id=cid, text=text,
                             parse_mode="HTML", disable_web_page_preview="true")
            if resp.get("ok"):
                sent += 1
            else:
                code = resp.get("error_code", 0)
                if code in (403, 400):
                    _mark_blocked(cid)
                errors.append(f"subscriber {cid}: {resp.get('description', '')}")
        except Exception as e:
            errors.append(f"subscriber {cid} exception: {e}")

    if channel_ok:
        url = SITE
        if channel_message_id:
            url = "https://t.me/NPZmap/%s" % channel_message_id
        DS.mark_published(state, key)
        DS.add_molniya_ref(state, event["headline"], url, key)
        DS.save_state(state)

    return {"channel_ok": channel_ok, "subscribers_sent": sent, "errors": errors,
            "skipped_duplicate": False, "key": key}


def _mark_blocked(chat_id):
    """Пометить подписчика как заблокировавшего бота."""
    subs_doc = jload(SUBS_PATH, {"subscribers": {}})
    info = subs_doc.get("subscribers", {}).get(str(chat_id), {})
    if info:
        info["status"] = "blocked"
        subs_doc["subscribers"][str(chat_id)] = info
        json.dump(subs_doc, open(SUBS_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 2 — Обычные новости (с кнопкой)
# ═══════════════════════════════════════════════════════════════════════════════

def _inline_keyboard_publish(text_for_channel, dedupe_key=None):
    """Создать inline-кнопки «Опубликовать» / «Отклонить» с payload-файлом
    (текст почти всегда > 64 байт лимита callback_data, поэтому пишем во
    временный файл pending-<id>.json и передаём только id)."""
    payload_id = str(int(time.time() * 1000))[-10:]
    payload_path = os.path.join(BOT_DIR, f"pending-{payload_id}.json")
    json.dump({
        "action": "publish_to_group",
        "text": text_for_channel,
        "dedupe_key": dedupe_key,
    }, open(payload_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    return {
        "inline_keyboard": [[
            {"text": "✅ Опубликовать", "callback_data": f"pub_to_group|{payload_id}"},
            {"text": "🚫 Отклонить", "callback_data": f"reject|{payload_id}"},
        ]]
    }


def publish_with_button(text, dry_run=False, dedupe_key=None):
    """
    TIER 2: Отправить новость владельцу (ADMIN_CHAT_ID) с кнопками
    «✅ Опубликовать» / «🚫 Отклонить». По нажатию «Опубликовать» —
    пересылка в @NPZmap (handle_callback → _do_publish_to_channel).

    text — текст новости (HTML, уже отрендеренный)
    dry_run — если True, только печатает что отправил бы
    dedupe_key — единый ключ дедупа (day_state), регистрируется при публикации
    Возвращает: {"sent": bool, "message_id": int|None, "error": str|None}
    """
    result = {"sent": False, "message_id": None, "error": None}

    if dry_run:
        print(f"\n{'='*60}")
        print(f"[DRY-RUN] TIER 2 — Обычные новости")
        print(f"{'='*60}")
        print(f"Текст:\n{text}")
        print(f"\nПолучатель (владелец): {ADMIN_CHAT_ID}")
        print(f"Кнопки: «✅ Опубликовать» → @NPZmap · «🚫 Отклонить»")
        print(f"{'='*60}\n")
        result["sent"] = True
        return result

    kb = _inline_keyboard_publish(text, dedupe_key=dedupe_key)
    try:
        resp = api_call(
            "sendMessage",
            chat_id=ADMIN_CHAT_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview="true",
            reply_markup=json.dumps(kb),
        )
        result["sent"] = resp.get("ok", False)
        result["message_id"] = resp.get("result", {}).get("message_id")
        if not result["sent"]:
            result["error"] = resp.get("description", "unknown")
    except Exception as e:
        result["error"] = str(e)

    return result


def publish_strike_tier2(strike, reason="", dry_run=False):
    """TIER 2 (единый прод-путь): рендерит через render_molniya (более лёгкая
    подача), проверяет дедуп, шлёт владельцу с кнопками подтверждения."""
    key = molniya_dedup_key(strike)
    state = DS.ensure_today(DS.load_state())
    if DS.is_published(state, key) and not dry_run:
        return {"sent": False, "message_id": None, "error": None, "skipped_duplicate": True, "key": key}

    event = strike_to_molniya_event(strike, reason=reason)
    text = R.render_molniya(event)
    res = publish_with_button(text, dry_run=dry_run, dedupe_key=key)
    res["skipped_duplicate"] = False
    res["key"] = key
    return res


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER (вызывается при нажатии inline-кнопки)
# ═══════════════════════════════════════════════════════════════════════════════

def handle_callback(callback_query):
    """
    Обработать callback query от inline-кнопки.

    callback_query — dict из Telegram callback_query update
    Возвращает: True если обработан, False если не наша кнопка
    """
    data = callback_query.get("data", "")
    query_id = callback_query.get("id")
    from_chat = callback_query.get("from", {}).get("id")

    # ── publish_to_group (подтверждение TIER 2) ──
    if data.startswith("pub_to_group|"):
        payload_id = data.split("|", 1)[1]
        payload_path = os.path.join(BOT_DIR, f"pending-{payload_id}.json")
        payload = jload(payload_path, {})
        text_to_publish = payload.get("text", "")
        dedupe_key = payload.get("dedupe_key")

        if text_to_publish:
            _do_publish_to_channel(text_to_publish)
            if dedupe_key:
                state = DS.ensure_today(DS.load_state())
                DS.mark_published(state, dedupe_key)
                DS.save_state(state)
            try:
                os.remove(payload_path)
            except Exception:
                pass
            api_call(
                "answerCallbackQuery",
                callback_query_id=query_id,
                text="✅ Опубликовано в @NPZmap!",
                show_alert=False,
            )
            try:
                msg = callback_query.get("message", {})
                api_call(
                    "editMessageText",
                    chat_id=msg.get("chat", {}).get("id"),
                    message_id=msg.get("message_id"),
                    text=text_to_publish + "\n\n✅ Опубликовано в @NPZmap",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return True

    # ── reject (отклонить TIER 2) ──
    if data.startswith("reject|"):
        payload_id = data.split("|", 1)[1]
        payload_path = os.path.join(BOT_DIR, f"pending-{payload_id}.json")
        payload = jload(payload_path, {})
        text_rejected = payload.get("text", "")
        try:
            os.remove(payload_path)
        except Exception:
            pass
        api_call(
            "answerCallbackQuery",
            callback_query_id=query_id,
            text="🚫 Отклонено, в канал не пойдёт.",
            show_alert=False,
        )
        try:
            msg = callback_query.get("message", {})
            api_call(
                "editMessageText",
                chat_id=msg.get("chat", {}).get("id"),
                message_id=msg.get("message_id"),
                text=(text_rejected or "") + "\n\n🚫 Отклонено",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return True

    # ── publish_to_group с прямым текстом (legacy JSON payload) ──
    if data.startswith("{"):
        try:
            payload = json.loads(data)
        except Exception:
            return False

        if payload.get("action") == "publish_to_group":
            text_to_publish = payload.get("text", "")
            if text_to_publish:
                _do_publish_to_channel(text_to_publish)
                api_call(
                    "answerCallbackQuery",
                    callback_query_id=query_id,
                    text="✅ Опубликовано в @NPZmap!",
                    show_alert=False,
                )
                try:
                    msg = callback_query.get("message", {})
                    api_call(
                        "editMessageReplyMarkup",
                        chat_id=msg.get("chat", {}).get("id"),
                        message_id=msg.get("message_id"),
                        reply_markup=json.dumps({"inline_keyboard": [[
                            {"text": "✅ Опубликовано", "callback_data": "noop"}
                        ]]}),
                    )
                except Exception:
                    pass
                return True

    # ── publish_to_group с прямым текстом (legacy) ──
    if data == "publish_to_group":
        api_call(
            "answerCallbackQuery",
            callback_query_id=query_id,
            text="⚠️ Нет текста для публикации",
            show_alert=True,
        )
        return True

    return False


def _do_publish_to_channel(text):
    """Отправить УЖЕ отрендеренный HTML-текст (render_molniya) в канал @NPZmap.
    НЕ прогонять через _format_molniya — тот добавляет legacy-префикс
    'МОЛНИЯ |' для сырых текстов из старого --major CLI-режима."""
    resp = api_call(
        "sendMessage",
        chat_id=CHANNEL_CHAT_ID,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview="true",
    )
    return resp.get("ok", False)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОВЕРКА ИЗ STRIKES.JSON (для интеграции с NEWSWATCH)
# ═══════════════════════════════════════════════════════════════════════════════

def classify_strikes_list(strikes, last_processed_index=0):
    """
    Проверить список ударов и вернуть классификации для новых.

    strikes — список ударов из strikes.json
    last_processed_index — индекс последнего обработанного удара
    Возвращает: list of (tier, text, classification_info)
    """
    results = []
    for i, strike in enumerate(strikes):
        if i < last_processed_index:
            continue
        tier, info = classify_news(strike)
        results.append({
            "index": i,
            "tier": tier,
            "info": info,
            "strike": strike,
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def _cli():
    """CLI-интерфейс для тестирования."""
    args = sys.argv[1:]
    dry_run = "--dry-run" in args

    if "--classify" in args:
        i = args.index("--classify")
        data_str = args[i + 1] if i + 1 < len(args) else "{}"
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            # Попробуем как Python dict repr
            print(f"ОШИБКА: Не удалось распарсить JSON: {data_str}")
            sys.exit(1)
        tier, info = classify_news(data)
        print(f"Классификация: TIER {1 if tier == 'major' else 2} ({tier})")
        print(f"  Заголовок: {info.get('headline', '')}")
        print(f"  Причина: {info.get('reason', '')}")
        sys.exit(0)

    if "--classify-file" in args:
        i = args.index("--classify-file")
        fpath = args[i + 1] if i + 1 < len(args) else ""
        if not fpath or not os.path.exists(fpath):
            print(f"ОШИБКА: Файл не найден: {fpath}")
            sys.exit(1)
        strikes_data = jload(fpath, {})
        strikes = strikes_data.get("strikes", [])
        if not strikes:
            print("Нет ударов в файле.")
            sys.exit(0)

        # Классифицируем все
        major_count = 0
        regular_count = 0
        for s in strikes[:20]:  # последние 20
            tier, info = classify_news(s)
            icon = "⚡" if tier == "major" else "📋"
            print(f"{icon} [{tier}] {s.get('city', '?')} — {s.get('target', '?')[:50]}")
            print(f"   Причина: {info.get('reason', '')}")
            if tier == "major":
                major_count += 1
            else:
                regular_count += 1

        print(f"\nИтого: {major_count} МОЛНИЙ, {regular_count} обычных (из {min(20, len(strikes))})")
        sys.exit(0)

    if "--major" in args:
        i = args.index("--major")
        text = args[i + 1] if i + 1 < len(args) else "Тестовый алерт"
        result = publish_major(text, dry_run=dry_run)
        print(f"Результат: {json.dumps(result, ensure_ascii=False, indent=2)}")
        sys.exit(0)

    if "--regular" in args:
        i = args.index("--regular")
        text = args[i + 1] if i + 1 < len(args) else "Обычное обновление"
        result = publish_with_button(text, dry_run=dry_run)
        print(f"Результат: {json.dumps(result, ensure_ascii=False, indent=2)}")
        sys.exit(0)

    # Справка
    print("""
radar_publish.py — Двухуровневая система оповещений

Команды:
  --classify <json>          Классифицировать событие из JSON
  --classify-file <path>     Классифицировать все удары из файла strikes.json
  --major <text>             Отправить МОЛНИЮ (TIER 1) — канал + подписчики
  --regular <text>           Отправить обычную новость (TIER 2) — с кнопкой
  --dry-run                  Не отправлять, только показать
""")


if __name__ == "__main__":
    _cli()
