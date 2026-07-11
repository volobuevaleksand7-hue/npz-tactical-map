# Инструкция Гермесу: слой-трипвайр «Newsader» (быстрый источник кандидатов)

**Дата:** 2026-07-11 · **Автор:** оркестратор (Mac) · **Статус:** ТЗ, к реализации на VPS
**Куда встраивается:** соседний rumor-источник к [[TZ_strike-candidates-pipeline]] — НЕ боевой слой.

## Идея

YouTube-канал **Newsader** (`channel_id UCS-cgYslpMpH5FkxJ2e0Vpg`) очень быстро выкладывает
ролики о свежих ударах по РФ: нефтебазы, НПЗ, портовые терминалы, суда теневого флота, мосты,
энергообъекты. Заголовки уже несут «город + тип цели» (напр. «ПЫЛАЮТ В ТВЕРИ И ПОД СТАВРОПОЛЕМ»,
«Ильский НПЗ», «ТАГАНРОГ… нефтебаза»). Нам нужен **трипвайр**: тянуть заголовки, вытаскивать
город+цель, класть как `confidence:"rumor"` кандидатов. В `strikes.json` — только после
ручного/Гермес-подтверждения, как и radar-кандидаты.

⚠️ Канал проукраинский и кликбейтный («ВСУ размазывают», «минус 18 судов»). Берём ТОЛЬКО факт
«что и где», в нейтральной формулировке. Триумфализм/пропаганду не тащим ([[npz-neutral-osint-guard]]).

## Жёсткое ограничение доступа (проверено 2026-07-11)

- ✅ **RSS-лента работает без авторизации, headless-безопасно** — это основной механизм на VPS:
  `https://www.youtube.com/feeds/videos.xml?channel_id=UCS-cgYslpMpH5FkxJ2e0Vpg`
  Отдаёт 15 последних: `<yt:videoId>`, `<title>`, `<published>` (ISO). Ни cookies, ни ключа.
- ❌ **Субтитры через yt-dlp на VPS блокируются** — «Sign in to confirm you're not a bot».
  yt-dlp без cookies не тянет ни метаданные, ни авто-титры. Субтитры — ТОЛЬКО опционально
  и только при наличии cookies-файла (см. ниже). Для трипвайра субтитры НЕ обязательны —
  заголовков достаточно.

## Что построить: `agents/newsader-watch.py`

Скриптовый слой (без claude), переиспользует хелперы из `agents/strike-candidates.py`
(`geocode_city`, `_city_pattern`, фетч `cities` с radar-map.ru). Логика:

1. Фетч RSS (urllib, UA задан), распарсить `videoId + title + published` (stdlib
   `xml.etree.ElementTree`, неймспейсы `yt:` и atom).
2. Для каждого нового videoId (дедуп по `data/newsader-seen.json` — множество id):
   - матч `NEWSADER_TARGET_RE` по ЗАГОЛОВКУ (список целей шире топливного — добавь суда/мост/энерго);
   - `geocode_city(title, cities)` — поставить город/координаты; без города всё равно кандидат
     (`geocoded:false`, «город уточняется»);
   - выпустить кандидат в схеме `to_candidate` из strike-candidates, но с:
     `source_label:"newsader"`, `source_url:"https://www.youtube.com/watch?v=<id>"`,
     `confidence:"rumor"`, `status:"candidate"`, `date/time` из `published` (+3ч → МСК),
     `target` = matched keyword, `title` нейтральный: «Сообщение о ударе по <город>» — БЕЗ
     копирования кликбейта из ролика.
3. Писать `data/newsader-candidates.json` (та же обёртка `generated_at/disclaimer/candidates[]`,
   что у strike-candidates). НЕ трогать `strikes.json`.
4. Пуш через `bash agents/git-sync.sh "data(newsader): $(date -u +%Y-%m-%dT%H:%MZ)"`
   (autostash-safe, см. [[npz-git-sync-hard-reset-hazard]]).

Расширенный фильтр целей (цели канала шире, чем только топливо):
```python
NEWSADER_TARGET_RE = re.compile(
  r"нпз|нефтезавод|нефтеперераб|нефтебаз|нефтехранил|нефтетерминал|нефтеналив|"
  r"терминал|топлив|бензин|гсм|"
  r"танкер|судн|суда|флот|порт|"
  r"мост|"
  r"энергообъект|энергомост|подстанц|грэс|тэц|электро|"
  r"впк|завод|склад", re.IGNORECASE)
```
Признак удара (STRIKE_RE) по заголовку НЕ требуй — весь канал про удары; хватает
цель-ключ ИЛИ геокодированный город + один из глаголов канала («горит/взорв/сожгл/пылают/поражен»).

### RSS-парсер (готовый кусок — вставить как есть)
```python
import urllib.request, xml.etree.ElementTree as ET
RSS = "https://www.youtube.com/feeds/videos.xml?channel_id=UCS-cgYslpMpH5FkxJ2e0Vpg"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
def fetch_rss():
    req = urllib.request.Request(RSS, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall("a:entry", NS):
        out.append({
            "id": e.find("yt:videoId", NS).text,
            "title": e.find("a:title", NS).text,
            "published": e.find("a:published", NS).text,  # ISO8601 UTC
        })
    return out
```

## Крон (VPS)

Каждые 20 мин — RSS дёшев, канал частит:
```cron
*/20 * * * * cd /root/npz-tactical-map && python3 agents/newsader-watch.py >> /root/logs/newsader.log 2>&1
```
Добавить `newsader-watch` в `healthcheck.py` WATCH-карту (порог ~60 мин), чтобы отставание
светилось на `health.json`.

## Опционально: обогащение субтитрами (за cookies-гейтом)

Только если оператор решит завести cookies. НЕ делать по умолчанию.
- Механизм (проверен на Маке): `yt-dlp --cookies <file> --write-auto-subs --sub-langs ru-orig,ru
  --sub-format vtt --skip-download` → снять таймкоды/теги → плоский текст.
- На Маке уже есть рабочий хелпер-образец: `~/Documents/Alarm NPZ/newsader.sh`
  (`list` / `subs <id>`, использует `--cookies-from-browser chrome`).
- ⚠️ **cookies YouTube = доступ к Google-сессии оператора.** Это чувствительно — решение оператора,
  не делегируй его. Если заводить: экспорт cookies.txt (Netscape) с Мака →
  `~/.newsader/cookies.txt` на VPS, `--cookies` вместо `--cookies-from-browser`; протухают —
  нужен рецепт обновления. Пока файла нет — скрипт работает в режиме «только заголовки».

## Инварианты (не нарушать)

- `newsader-candidates.json` — НЕ боевой слой: `status:"candidate"`, `confidence:"rumor"`.
  В `strikes.json` авто-НЕ вливается; промоушен только через подтверждение (GDELT/FIRMS/ручное).
- Нейтральный тон, кликбейт канала не копировать в `title` кандидата ([[npz-neutral-osint-guard]],
  sanitize-strikes в pre-commit срежет вербатим/пропаганду при коммите).
- Запрет ПВО-меток в силе ([[npz-no-pvo-marking]]).
- Дедуп по videoId обязателен (иначе каждый прогон плодит дубли).
- Изоляция от боевого архива: shrink-guard strikes.json Newsader НЕ касается.

## Проверка после реализации

`python3 agents/newsader-watch.py --dry-run` на ночи с реальными ударами должен дать
≥1 кандидат с городом (Таганрог/Азов/Тверь/Ильский и т.п.). Пустой результат при явных
ударных заголовках = баг фильтра/геокодера.
