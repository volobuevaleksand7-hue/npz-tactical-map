#!/usr/bin/env python3
"""
@NpzFuel_Bot — бот подписки на уведомления об угрозах БПЛА/ракет
для проекта «Топливный фронт РФ» (npz-tactical-map.vercel.app).

Команды:
  /start       — приветствие и авто-подписка
  /status      — текущий статус подписки
  /radar       — текущая радар-картина
  /regions     — выбор регионов (инлайн-кнопки)
  /interval N  — интервал напоминаний (мин)
  /pause       — приостановить уведомления
  /resume      — возобновить уведомления
  /unsubscribe — отписаться
  /help        — справка
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ─── paths ───
HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", os.path.join(HOME, "npz-tactical-map"))
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
RADAR_DATA = os.path.join(REPO, "data", "radar-state.json")
SITE = "https://npz-tactical-map.vercel.app"

# ─── NPZ регионы ───
NPZ_REGIONS = [
    "Краснодарский край", "Ленинградская обл.", "Ярославская обл.",
    "Москва", "Московская обл.", "Республика Крым", "г. Севастополь",
    "Волгоградская обл.", "Самарская обл.", "Саратовская обл.", "Ростовская обл.",
]
REGION_ALIASES = {
    "все": "all", "всё": "all", "all": "all",
    "москва и мо": "Москва", "московская область": "Московская обл.",
    "ленинградская область": "Ленинградская обл.", "питер": "Ленинградская обл.",
    "краснодар": "Краснодарский край", "кубань": "Краснодарский край",
    "ростов": "Ростовская обл.", "самара": "Самарская обл.",
    "саратов": "Саратовская обл.", "волгоград": "Волгоградская обл.",
    "ярославль": "Ярославская обл.", "крым": "Республика Крым",
    "севастополь": "г. Севастополь",
}

# короткие имена для кнопок
REGION_SHORT = {
    "Краснодарский край": "Краснодар",
    "Ленинградская обл.": "Ленинград",
    "Ярославская обл.": "Ярославль",
    "Москва": "Москва",
    "Московская обл.": "МО",
    "Республика Крым": "Крым",
    "г. Севастополь": "Севастополь",
    "Волгоградская обл.": "Волгоград",
    "Самарская обл.": "Самара",
    "Саратовская обл.": "Саратов",
    "Ростовская обл.": "Ростов",
}

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("npz-bot")


# ─── JSON helpers ───
def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_subs():
    return jload(SUBS_PATH, {"subscribers": {}})


def save_subs(data):
    jsave(SUBS_PATH, data)


def normalize_region(name):
    name = str(name or "").strip()
    if not name:
        return None
    if name in REGION_ALIASES:
        return REGION_ALIASES[name]
    if name in NPZ_REGIONS:
        return name
    lower = name.lower()
    for alias, canonical in REGION_ALIASES.items():
        if alias.lower() in lower or lower in alias.lower():
            return canonical
    for region in NPZ_REGIONS:
        if lower in region.lower() or region.lower() in lower:
            return region
    return None


def ensure_sub(chat_id, name="", subs=None):
    """Вернуть (создав при необходимости) запись подписчика.
    Если передан subs — работаем ПО НЕМУ и НЕ сохраняем (сохранит вызывающий тем же subs);
    иначе — сами load+save. Чинит баг «настройки не сохраняются»: хендлер делал load_subs()
    и ensure_sub() (со своим load), правил вторую копию, а сохранял первую."""
    own = subs is None
    if own:
        subs = load_subs()
    sub = subs["subscribers"].setdefault(str(chat_id), {
        "status": "active",
        "since": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "src": "bot",
        "name": str(name or ""),
        "alerts": {"enabled": True, "regions": ["all"], "interval_min": 60},
    })
    if name and not sub.get("name"):
        sub["name"] = str(name)
    sub.setdefault("alerts", {"enabled": True, "regions": ["all"], "interval_min": 60})
    if own:
        save_subs(subs)
    return sub


def user_display(update: Update):
    u = update.effective_user
    parts = []
    if u.first_name:
        parts.append(u.first_name)
    if u.last_name:
        parts.append(u.last_name)
    name = " ".join(parts) if parts else (u.username or str(u.id))
    return name, u.id


def region_list(regions):
    if not regions or "all" in regions:
        return "все регионы"
    short = [REGION_SHORT.get(r, str(r)) for r in regions]
    return ", ".join(short)


def get_sub_regions(chat_id):
    subs = load_subs()
    sub = subs["subscribers"].get(str(chat_id), {})
    alerts = sub.get("alerts", {})
    regions = alerts.get("regions", ["all"])
    is_all = "all" in regions
    return regions, is_all


def set_sub_regions(chat_id, regions):
    subs = load_subs()
    sub = subs["subscribers"].setdefault(str(chat_id), {})
    sub.setdefault("alerts", {"enabled": True, "regions": ["all"], "interval_min": 60})
    sub["alerts"]["regions"] = regions
    save_subs(subs)


# ─── инлайн-клавиатура регионов ───
def build_regions_keyboard(chat_id):
    regions, is_all = get_sub_regions(chat_id)
    keyboard = []
    # по 2 кнопки в ряд
    row = []
    for region in NPZ_REGIONS:
        selected = is_all or region in regions
        label = f"{'✅' if selected else '⬜'} {REGION_SHORT.get(region, region)}"
        row.append(InlineKeyboardButton(label, callback_data=f"reg:{region}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    # строка: Все / Готово
    keyboard.append([
        InlineKeyboardButton(
            f"{'✅' if is_all else '⬜'} Все регионы",
            callback_data="reg:all"
        ),
        InlineKeyboardButton("✅ Готово", callback_data="reg:done"),
    ])
    return InlineKeyboardMarkup(keyboard)


# ─── команды ───
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name, chat_id = user_display(update)
    sub = ensure_sub(chat_id, name)
    alerts = sub["alerts"]
    regions = alerts["regions"]
    interval = alerts["interval_min"]

    text = (
        f"👋 Привет, {name}!\n\n"
        f"Ты подписан на уведомления об угрозах БПЛА и ракет.\n\n"
        f"⚙️ Твои настройки:\n"
        f"• Регионы: {region_list(regions)}\n"
        f"• Интервал: каждые {interval} мин\n"
        f"• Уведомления: {'✅ включены' if alerts['enabled'] else '⏸ приостановлены'}\n\n"
        f"Выбери регионы 👇 или используй команды."
    )
    await update.message.reply_text(
        text,
        reply_markup=build_regions_keyboard(chat_id),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id = user_display(update)
    subs = load_subs()
    sub = subs["subscribers"].get(str(chat_id))

    if not sub or sub.get("status") != "active":
        await update.message.reply_text("Ты не подписан. Напиши /start чтобы подписаться.")
        return

    alerts = sub.get("alerts", {})
    text = (
        f"📊 Статус подписки:\n\n"
        f"• Статус: {'✅ активна' if sub.get('status') == 'active' else 'неактивна'}\n"
        f"• Уведомления: {'✅ включены' if alerts.get('enabled') else '⏸ приостановлены'}\n"
        f"• Регионы: {region_list(alerts.get('regions', ['all']))}\n"
        f"• Интервал: каждые {alerts.get('interval_min', 60)} мин\n"
        f"• Подписан с: {sub.get('since', '?')}\n\n"
        f"/regions — настроить регионы\n/interval — интервал\n/pause — пауза"
    )
    await update.message.reply_text(text)


async def cmd_radar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        radar = jload(RADAR_DATA, {})
        cities = radar.get("cities", {})
        active_npz = []
        for key, city in (cities.items() if isinstance(cities, dict) else []):
            region = city.get("region", "")
            norm = normalize_region(region)
            if norm and norm in NPZ_REGIONS:
                bpla = bool(city.get("bpla"))
                rocket = bool(city.get("rocket") or city.get("rk"))
                if bpla or rocket:
                    threats = []
                    if bpla:
                        threats.append("БПЛА")
                    if rocket:
                        threats.append("РК")
                    active_npz.append(f"🔴 {norm} — {'+'.join(threats)}")

        if active_npz:
            text = "⚠️ Активные угрозы в регионах НПЗ:\n\n" + "\n".join(active_npz)
        else:
            text = "🟢 В регионах НПЗ угроз не обнаружено."

        msk = datetime.now(timezone.utc) + timedelta(hours=3)
        text += f"\n\n🕐 {msk.strftime('%H:%M')} МСК\nРадар: {SITE}/radar.html"
        await update.message.reply_text(text, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"radar error: {e}")
        await update.message.reply_text("Не удалось загрузить данные радара. Попробуй позже.")


async def cmd_regions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id = user_display(update)
    subs = load_subs()
    sub = subs["subscribers"].get(str(chat_id))

    if not sub or sub.get("status") != "active":
        await update.message.reply_text("Сначала подпишись: /start")
        return

    regions = sub.get("alerts", {}).get("regions", ["all"])
    await update.message.reply_text(
        f"📍 Твои регионы: {region_list(regions)}\nНажми на регион чтобы добавить/убрать:",
        reply_markup=build_regions_keyboard(chat_id),
    )


async def on_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # "reg:Краснодарский край" / "reg:all" / "reg:done"
    _, chat_id = user_display(update)

    if not data.startswith("reg:"):
        return

    action = data[4:]  # "Краснодарский край" / "all" / "done"

    if action == "done":
        regions, _ = get_sub_regions(chat_id)
        await query.edit_message_text(
            f"✅ Сохранено: {region_list(regions)}\n"
            f"Интервал: /interval | Пауза: /pause",
            reply_markup=None,
        )
        return

    regions, is_all = get_sub_regions(chat_id)

    if action == "all":
        if is_all:
            # снять "все" → пустой список
            set_sub_regions(chat_id, [])
        else:
            set_sub_regions(chat_id, ["all"])
    else:
        # конкретный регион
        if is_all:
            # был "all" → убрать all, оставить только этот
            new_regions = [action]
        elif action in regions:
            new_regions = [r for r in regions if r != action]
        else:
            new_regions = regions + [action]

        if not new_regions:
            new_regions = ["all"]
        set_sub_regions(chat_id, new_regions)

    # обновить клавиатуру
    regions, _ = get_sub_regions(chat_id)
    await query.edit_message_text(
        f"📍 Твои регионы: {region_list(regions)}\nНажми на регион чтобы добавить/убрать:",
        reply_markup=build_regions_keyboard(chat_id),
    )


TIMER_OPTIONS = [
    (10, "⏱ 10м"), (30, "⏱ 30м"), (60, "⏱ 1ч"),
    (180, "⏱ 3ч"), (360, "⏱ 6ч"), (720, "⏱ 12ч"),
]

def build_timer_keyboard(current_interval=60):
    """Inline-кнопки выбора интервала."""
    row = []
    for minutes, label in TIMER_OPTIONS:
        prefix = "✅ " if minutes == current_interval else ""
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"timer:{minutes}"))
    changes_prefix = "✅ " if current_interval == 0 else ""
    row.append(InlineKeyboardButton(f"{changes_prefix}🔔 По изменениям", callback_data="timer:changes"))
    return InlineKeyboardMarkup([row])


def interval_text(interval_min):
    """Человекочитаемый интервал."""
    if interval_min == 0:
        return "только при изменениях"
    if interval_min < 60:
        return f"каждые {interval_min} мин"
    hours = interval_min // 60
    return f"каждые {hours} ч" if hours > 1 else "каждый час"


async def on_timer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки таймера."""
    query = update.callback_query
    await query.answer()
    _, chat_id = user_display(update)
    data = query.data  # "timer:30" or "timer:changes"

    raw = data.split(":", 1)[1]
    subs = load_subs()
    sub = ensure_sub(chat_id, "", subs=subs)

    if raw == "changes":
        sub["alerts"]["interval_min"] = 0
        new_interval = 0
    else:
        try:
            new_interval = int(raw)
        except ValueError:
            new_interval = 60
        sub["alerts"]["interval_min"] = new_interval

    save_subs(subs)

    # Обновить клавиатуру
    kb = build_timer_keyboard(new_interval)
    await query.edit_message_reply_markup(reply_markup=kb)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏱ Интервал: {interval_text(new_interval)}",
    )


async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    name, chat_id = user_display(update)

    subs = load_subs()
    sub = ensure_sub(chat_id, name, subs=subs)

    # Если передан аргумент — изменить интервал (обратная совместимость)
    if args:
        try:
            val = int(args[0])
            if val < 5:
                await update.message.reply_text("Минимальный интервал — 5 минут.")
                return
            if val > 1440:
                await update.message.reply_text("Максимальный интервал — 1440 мин (24 часа).")
                return
        except ValueError:
            await update.message.reply_text("Пример: /interval 30")
            return
        sub["alerts"]["interval_min"] = val
        save_subs(subs)

    interval = sub.get("alerts", {}).get("interval_min", 60)
    kb = build_timer_keyboard(interval)
    await update.message.reply_text(
        f"⏱ Интервал напоминаний: {interval_text(interval)}.\n"
        f"Нажми кнопку чтобы изменить:",
        reply_markup=kb,
    )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id = user_display(update)
    subs = load_subs()
    sub = subs["subscribers"].get(str(chat_id))
    if not sub:
        await update.message.reply_text("Сначала подпишись: /start")
        return
    sub.setdefault("alerts", {})["enabled"] = False
    save_subs(subs)
    await update.message.reply_text("⏸ Уведомления приостановлены. /resume чтобы возобновить.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id = user_display(update)
    subs = load_subs()
    sub = subs["subscribers"].get(str(chat_id))
    if not sub:
        await update.message.reply_text("Сначала подпишись: /start")
        return
    sub.setdefault("alerts", {})["enabled"] = True
    save_subs(subs)
    await update.message.reply_text("✅ Уведомления возобновлены.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, chat_id = user_display(update)
    subs = load_subs()
    sub = subs["subscribers"].get(str(chat_id))
    if not sub:
        await update.message.reply_text("Ты не подписан.")
        return
    sub["status"] = "inactive"
    save_subs(subs)
    await update.message.reply_text("👋 Ты отписался. Чтобы вернуться: /start")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 @NpzFuel_Bot — уведомления об угрозах НПЗ\n\n"
        "Команды:\n"
        "/start — подписаться и выбрать регионы\n"
        "/status — статус подписки\n"
        "/radar — текущая обстановка\n"
        "/regions — выбрать регионы (кнопки)\n"
        "/interval 30 — интервал напоминаний\n"
        "/pause — пауза уведомлений\n"
        "/resume — возобновить\n"
        "/unsubscribe — отписаться\n"
        "/help — эта справка\n\n"
        f"Карта: {SITE}/radar.html"
    )
    await update.message.reply_text(text)


# ─── inline-кнопки публикации молнии TIER2 (pub_to_group|/reject|/publish_to_group/{json}) ───
# radar_publish.handle_callback ждёт raw-dict Telegram callback_query; PTB даёт объект → .to_dict().
# Раньше эти кнопки дренил poll.py из publish-vps.sh, конфликтуя с ЭТИМ демоном за getUpdates
# (один токен = один потребитель getUpdates → 409). Теперь обрабатывает сам демон, в реальном времени.
async def on_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from radar_publish import handle_callback
        handle_callback(update.callback_query.to_dict())
    except Exception as e:
        logger.error(f"publish callback error: {e}")


# ─── main ───
def main():
    token_path = os.path.join(BOT_DIR, "token")
    if not os.path.exists(token_path):
        logger.error(f"Token file not found: {token_path}")
        sys.exit(1)

    with open(token_path) as f:
        token = f.read().strip()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("radar", cmd_radar))
    app.add_handler(CommandHandler("regions", cmd_regions))
    app.add_handler(CommandHandler("interval", cmd_interval))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(on_region_callback, pattern="^reg:"))
    app.add_handler(CallbackQueryHandler(on_timer_callback, pattern="^timer:"))
    app.add_handler(CallbackQueryHandler(
        on_publish_callback, pattern=r"^(pub_to_group\||reject\||publish_to_group|\{)"))

    logger.info("Starting @NpzFuel_Bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
