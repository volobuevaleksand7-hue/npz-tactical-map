# Handoff — npz-tactical-map — 2026-07-17

## Status
Инцидент публикации закрыт, /refineries стал самогенерируемым, добавлена /krupnejshie-npz-rossii, 7 карточек НПЗ в проде (3 мои + 4 от параллельной сессии), sitemap чист. Next: карточка Салаватского НПЗ (2 удара) + догон /refineries и /talony под свежие данные.

## Read first (in order)
1. `docs/agents/SESSION_HANDOFF_2026-07-17.md` — этот файл
2. auto-memory: npz-refineries-data-drift, npz-krupnejshie-npz-page, npz-seo-page-creation-mechanism, npz-parallel-wave3-collision
3. `CLAUDE.md` репо
4. `docs/agents/tz-seo-wave3-2026-07.md`

## Сделано за 16-17.07 (в проде)
- Публикация вставала на 6ч — разблокировано, watchdog видит зависание (d92c8b77), корень (news-sitemap/rss не коммитились) устранён (c92b1825).
- @NpzFuel_Bot: убит дубль-процесс (Conflict-цикл).
- /refineries — полностью генерируемый: FAQ/JSON-LD из данных (791f8d86), check-стража чинена по регистру (3a02f907), перелинковка на 18 карточек (9d573d75), hero-числа+прямой ответ (c7d368b9). gen-refineries в publish-vps каждые 6ч.
- 7 карточек НПЗ: Сызранский/Афипский/Туапсинский (71fb50fd) + Волгоградский/Астраханский ГПЗ/Ангарский/Новокуйбышевский от параллельной сессии (dad2784c) — была коллизия, мои дубли выброшены.
- Новая /krupnejshie-npz-rossii — рейтинг по мощности (179c5d41), вторая RANK_PAGE в gen-refineries.py, интент разведён с /refineries.
- Аудит ссылок+sitemap: 1 битая починена (5cce1da9), sitemap чист (138 URL, 0 дублей/битых).

## In-session decisions
- **Карточки НПЗ строго из fuel-state.json+strikes.json**, нейтральный тон, честно тоньше при отсутствии ударов (прецедент taif-nk); линковка через CARDS в генераторе, не руками.
- **/krupnejshie-npz-rossii без разбивки по городам**: поле city пусто у всех 32, выдумывать нельзя — география уже в «по регионам».

## Next step
Карточка /npz/salavat-npz (Газпром нефтехим Салават, 2 удара за 4 дня, не дубль) через publish-npz.py (REGISTRY + drafts/npz/ + CARDS).

## Открытые долги
- wave-events.json не закрыл ночную волну БПЛА 16→17.07 (10+ регионов) — проверить детектор.
- Замер SEO-эффекта — только в W30 после 19.07 (лаг Вебмастера).

## First message
```
Продолжаю npz-tactical-map. Не начинай работу, пока не скажу.

Прочитай по порядку:
1. `docs/agents/SESSION_HANDOFF_2026-07-17.md`
2. auto-memory: npz-refineries-data-drift, npz-krupnejshie-npz-page, npz-seo-page-creation-mechanism, npz-parallel-wave3-collision
3. `CLAUDE.md` репо + `docs/agents/tz-seo-wave3-2026-07.md`

Первый шаг: карточка /npz/salavat-npz (Газпром нефтехим Салават, 2 удара за 4 дня) через agents/publish-npz.py.

Жди мою команду.
```
