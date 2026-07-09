# ТЗ: юзабилити мобильной/PWA-версии — сводный аудит

**Дата:** 2026-07-09 · **Базовая версия:** v1.9.1 · **Целевая версия фиксов:** v1.10.0
**Аудиторы:** DeepSeek V4 Flash + MiMo v2.5 Pro + Codex (раздел ниже) · оркестратор Claude Opus 4.8
**Триггер:** жалобы владельца — кнопки перекрываются меню, ломаная адаптация под экраны, громоздкая кнопка установки, нет инструкций с картинками, нет информирования об установленной PWA.

Уже исправлено в v1.9.1 (вне этого ТЗ): восстановлен архив ударов (148), нормализация `location[]→lat/lon`, развязка слоя ударов от радар-прокси, счётчик 🛩/🚀 на панели «Угрозы НПЗ».

---

## 🔴 Блок 1. Перекрытия элементов (критично)

| # | Проблема | Файл:строка | Источник |
|---|---|---|---|
| 1.1 | `safe-area-inset` отсутствует: нет `viewport-fit=cover`, нижняя навигация `.tabs` и FAB попадают под индикатор «домой» на iPhone | index.html:6, styles.css | MiMo |
| 1.2 | Bottom-sheet (`.mob-sheet`, z-index:2000) перекрывает нижнюю навигацию (z-index:100) и FAB (z-index:25) — FAB нечем закрыть sheet | styles.css:417,425,494,2000 | оба |
| 1.3 | `.topctl` на ≤820px: `overflow:hidden` режет крайние кнопки (в т.ч. «Установить приложение») без скролла и индикатора | styles.css:480–484 | MiMo |
| 1.4 | Strikebar перекрывается со status-strip (z-index 25 vs 28); на radar.html seo-strip конфликтует с panel | styles.css:535,631; radar.html:70 | оба |
| 1.5 | Radar: `.disclaimer` и `.legend-toggle` накладываются на мобильных (оба absolute, bottom-зона) | radar.html:151–153,268 | MiMo |
| 1.6 | Tab-dropdown (fixed, z-index:300) перекрывает FAB; не закрывается тапом по карте | styles.css:693–699 | MiMo |

**Фиксы:** `viewport-fit=cover` + `env(safe-area-inset-*)` на `.tabs`/`.topbar`; FAB выше sheet (z-index:2500) либо sheet с padding под навбар; `.topctl` → `overflow-x:auto`; strikebar `top:48px` на мобильных; disclaimer на мобильных прятать (дублируется seo-strip); dropdown закрывать по тапу на карту.

## 🔴 Блок 2. Адаптация под ширины

| # | Проблема | Файл:строка | Источник |
|---|---|---|---|
| 2.1 | Провал 401–819px: нет мобильной вёрстки на широких телефонах/фаблетах | styles.css:400,820 | DeepSeek |
| 2.2 | Нет landscape-ориентации вообще | styles.css | DeepSeek |
| 2.3 | Переполнение вкладок на 700–820px | styles.css:85–86,474 | DeepSeek |
| 2.4 | Gap 820–920px: strikebar `max-width:calc(100vw-560px)` → ~260px, контролы не влезают | styles.css:469–475 | MiMo |
| 2.5 | Radar: нет breakpoint 769–1024px — panel 340px + feed 320px давят карту | radar.html:175–180 | MiMo |
| 2.6 | Две карточки col-left/card-right по 52vh — конфликт на средних высотах | styles.css:519–522 | DeepSeek |

**Фиксы:** ввести промежуточный breakpoint ~640/920px; `@media (orientation:landscape) and (max-height:500px)`; strikebar `flex-wrap:wrap; max-width:none` на ≤920px; radar ≤1024px — прятать feed, panel 280px.

## 🟡 Блок 3. Кнопка «Установить приложение» + PWA-жизненный цикл

| # | Проблема | Файл:строка | Источник |
|---|---|---|---|
| 3.1 | Кнопка — просто ссылка на /install, не PWA-промпт; нет `beforeinstallprompt` | index.html:129, app.js | все |
| 3.2 | Кнопка не скрывается после установки; нет `appinstalled`, нет проверки `display-mode: standalone` | app.js | все |
| 3.3 | Кнопка громоздкая; на 821–1240px `.tg-subscribe` сжимается до иконки, `.install-link` — нет | styles.css:106–109,702–711 | оба |
| 3.4 | SW-регистрация с пустым `.catch()`: нет toast «доступна новая версия» (`updatefound`) | index.html:364 | DeepSeek |

**Фикс (ядро блока):** компактная иконка-кнопка 📲 (28×28, title-tooltip), сжатие в том же breakpoint что `.tg-subscribe`; JS: `beforeinstallprompt` → показать кнопку → `prompt()` по клику; `appinstalled` → скрыть кнопку + **toast «✅ Приложение установлено»** (требование владельца — информирование об установке); при `matchMedia('(display-mode: standalone)')` — скрывать кнопку и Telegram-баннер (`@media (display-mode: standalone)` в CSS). Ссылка на /install остаётся фолбэком для iOS (там нет beforeinstallprompt).

## 🟡 Блок 4. Инструкции с картинками (страница /install и справка)

| # | Проблема | Файл:строка | Источник |
|---|---|---|---|
| 4.1 | /install — статический текст: нет accordion, нет скриншотов «куда нажать», все 3 платформы развёрнуты сразу | install.html:44–71 | оба |
| 4.2 | Нет страницы «Как пользоваться картой» (FAB, sheet, слои, раскраска регионов — без подсказок) | — | DeepSeek |
| 4.3 | Radar: `.about-radar` полностью скрыт на мобильных — справка потеряна | radar.html:297 | MiMo |

**Фиксы:** `<details>/<summary>` accordion по платформам (🍏 iOS / 🤖 Android / 💻 Desktop), внутри — скриншоты шагов (`assets/install-*.png`, генерить через Codex image_gen — правило обложек); стили мимикрируют под `.card-h--clickable`. Страница /help или accordion-подсказка в boot-экране + ссылка «❓ Как пользоваться» в analytics-dropdown. На радаре about → accordion вместо `display:none`.

## 🟢 Блок 5. PWA-полировка

| # | Проблема | Файл | Источник |
|---|---|---|---|
| 5.1 | Manifest без `shortcuts` (на /radar, /news), `screenshots`, `id` — Chrome показывает бедный промпт | manifest.webmanifest | MiMo |
| 5.2 | SW SHELL не кэширует /radar, /news, /install — офлайн отдаёт `/` | sw.js:9–10 | MiMo |
| 5.3 | FAB focus-visible может обрезаться overflow родителя | styles.css:666–671 | MiMo |

## 🔴 Блок 6. Данные (вне UI, но обязательный — регрессия повторилась)

| # | Проблема | Фикс |
|---|---|---|
| 6.1 | Облачный коллектор 08.07 23:20Z затёр архив strikes.json (147→0→5). Вторая такая регрессия | Инструкция Гермесу (docs/agents/): коллектор ТОЛЬКО дописывает, перезапись архива запрещена |
| 6.2 | Нет страховки от усечения | Guard в pre-commit (sanitize-strikes.py): блокировать коммит, если число strikes падает более чем на 10% — обход только явным флагом |

---

## Порядок работ (рекомендация)

1. **v1.9.2 (данные):** блок 6 — guard + инструкция Гермесу. Мелкий, срочный.
2. **v1.10.0 (UI):** блоки 1→2→3 одним релизом (перекрытия, адаптация, install-UX). Порядок внутри: 1.1 → 1.2 → 2.1 → 2.2 → 3.1+3.2 → 1.3 → остальное.
3. **v1.11.0 (справка):** блок 4 (accordion + скриншоты) + блок 5.

Каждый релиз: SemVer, CHANGELOG.md, version.json, проверка опубликованного релиза (Karpathy §6). Скриншоты для /install генерятся Codex image_gen (правило обложек — только Codex).

## Раздел Codex

_(дозаполняется по завершении прогона Codex — см. ниже в файле или следующий коммит)_
