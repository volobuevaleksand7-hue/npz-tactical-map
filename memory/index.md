---
name: index
description: Карта памяти проекта npz-tactical-map — список листиков, что в каждом и когда его читать.
type: fact
trust: internal
approved_by: 2ea839a6-91da-4d77-a654-1596ac52fe93
---

# Память проекта «НПЗ — тактическая карта»

Это карта памяти, а не сама память. Прочитай через Read те листики, что относятся к твоей текущей задаче, остальные не тяни — каждый написан так, чтобы отвечать на вопрос «что я сломаю, если не буду это знать».

Проект: OSINT-дашборд состояния НПЗ/топлива/логистики РФ. Статический сайт на Vercel, данные в `data/*.json`, пишутся cron-агентами на VPS (Hermes) и Claude-сессиями на Маке. Репозиторий публичный, проект анонимный — см. `rules.md`.

## Обязательно перед любой правкой

- **[rules.md](rules.md)** — жёсткие запреты: нейтральный тон, деанон-границы, защита UI-shell, запрет разрушительного git, архивы только дописываются, обложки только через Codex.
- `CLAUDE.md` в корне репо — канон расположения (текущий репозиторий/аккаунт/VPS), stack, guardrails. Читать вместе с этим файлом, не вместо.

## decisions/ — принятые решения и почему так

- **[ui-shell-release-gate.md](decisions/ui-shell-release-gate.md)** — почему `index.html`/`styles.css`/`app.js`/`radar.html`/`version.json`/`CHANGELOG.md` заперты за `ALLOW_FRONTEND_RELEASE=1`. Читать перед правкой фронтенда.
- **[archive-datasets-append-only.md](decisions/archive-datasets-append-only.md)** — почему `strikes.json`/`fuel-voices.json` только дописываются, и как по-разному охраняются гвардами (блок vs авто-восстановление). Читать перед правкой коллекторов/архивов.
- **[seo-one-intent-per-page.md](decisions/seo-one-intent-per-page.md)** — почему меню генерится из `data/seo-topics.jsonl`, и обязательный 3-уровневый чек на дубль перед новой страницей. Читать перед созданием/правкой любой SEO-страницы.
- **[session-zones-shared-worktree.md](decisions/session-zones-shared-worktree.md)** — как `.claude/zones/*.zone` предупреждает о столкновении параллельных сессий, и почему возраст зоны считается через `git log`, а не mtime. Читать при долгой работе рядом с другими активными агентами.
- **[guard-block-vs-autoheal-policy.md](decisions/guard-block-vs-autoheal-policy.md)** — критерий, когда pre-commit гвард блокирует коммит, а когда чинит-и-пропускает. Читать перед добавлением нового гварда в `.githooks/pre-commit`.
- **[covers-via-codex-pipeline.md](decisions/covers-via-codex-pipeline.md)** — почему обложки только через Codex + PIL-бэкстоп. Читать, если чинишь тикет «обложка = заглушка».

## facts/ — грабли и режимы отказа

- **[generated-file-not-staged-dirty-tree.md](facts/generated-file-not-staged-dirty-tree.md)** — генератор пишет файл, коммит про него не знает → дерево вечно грязное → встаёт публикация всему флоту. Рецидив ×4+. Читать, пиша любой скрипт, создающий файлы на диске.
- **[regenerator-drops-manual-fields.md](facts/regenerator-drops-manual-fields.md)** — регенератор пересобирает датасет с нуля и стирает поля, добавленные вручную другим прогоном. Рецидив ×3+. Читать перед прогоном любого `fetch-*`/`gen-*`-скрипта на файле с ручными полями.
- **[hidden-second-scheduler.md](facts/hidden-second-scheduler.md)** — на VPS расписание живёт в 3 местах, `/root/.hermes/cron/jobs.json` невидим для `crontab -l`/syslog. Читать при диагностике дублей публикации.
- **[shared-worktree-git-hygiene.md](facts/shared-worktree-git-hygiene.md)** — какой git разрушал общее дерево (autostash-клоббер ×3, `reset --hard`), и как не спутать отставший worktree с потерей работы. Читать перед любой git-операцией вне `git-sync.sh`.
- **[warehouse-geo-matching-fragility.md](facts/warehouse-geo-matching-fragility.md)** — три независимых бага матчинга складов WB/Ozon к ударам (ghost-дубли, скобки в имени, регэкс бренда цепляет соседей). Читать перед правкой `fetch-warehouses.py` или атрибуции склад↔удар.
- **[stale-shell-and-cache-traps.md](facts/stale-shell-and-cache-traps.md)** — три способа показать пользователю устаревшую версию сайта через Vercel-кэш/service worker. Читать при жалобе «вижу старую версию» или перед правкой `vercel.json`/`sw.js`.
- **[json-array-bloat-and-migration-verification.md](facts/json-array-bloat-and-migration-verification.md)** — табличная схема режет вес большого однородного JSON лучше точечных твиков; любую миграцию проверять round-trip тем же декодером. Читать перед оптимизацией/миграцией `data/*.json`.
- **[metric-drift-llm-recompute.md](facts/metric-drift-llm-recompute.md)** — headline-метрика национального баланса врала ×3, потому что LLM путает похожие поля при ручном пересчёте на каждом синке. Читать перед доверием к `national_balance`/прозе агента про доли/проценты.
- **[fleet-health-false-signals.md](facts/fleet-health-false-signals.md)** — «флот мёртв»/индикаторы здоровья лгут ×2 разными механизмами (обнулённый heartbeats, окно с TTL спутано с архивом). Читать перед тем, как доверять плашке здоровья флота.
- **[subagent-delegation-and-verification.md](facts/subagent-delegation-and-verification.md)** — субагенты пусто выходят из цепочечного делегирования, MiMo выдумывает числа. Читать перед делегированием сбора данных/ресёрча.
- **[cloned-template-inherits-foreign-code.md](facts/cloned-template-inherits-foreign-code.md)** — клон HTML-шаблона тащит чужую JSON-LD, copy-paste inline-скрипта расходится в копиях. Читать при создании страницы из чужого каркаса или дублировании JS/CSS на много лендингов.
