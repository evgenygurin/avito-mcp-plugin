# Phase 0 — Documentation Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать всю документацию, скилы и манифесты `avito-mcp-plugin` под
целевой дизайн полнофункционального парсера каталога Avito (спека
[2026-07-18-avito-parser-design.md](../specs/2026-07-18-avito-parser-design.md)),
не трогая рантайм-код (он остаётся рабочим до Фазы 1).

**Architecture:** Только документация. Удаляются pure-doc артефакты (2 скила +
`docs/avito-legal.md`); остальные доки/манифесты/2 скила переписываются под целевой
дизайн (7 тулз, новая структура, новый env, без legal-guardrails и официального API).
Тулзы помечаются статусом «план», как принято в репозитории. Код официального API
физически удаляется в Фазе 1.

**Tech Stack:** Markdown, JSON/TOML-манифесты, `scripts/check_versions.py`,
`claude plugin validate`.

**Content authority:** источник истины по содержанию (список тулз, env, структура
модулей, фазы) — спека. Задачи ниже ссылаются на её секции, не дублируя таблицы.

**Convention:** во всех переписанных доках официальный API и legal-guardrails
**не упоминаются как текущие**; где нужен исторический след — короткая пометка
«удалено в пользу целевого фичесета парсинга, см. spec». Статусы тулз — 🔜 «план».

---

### Task 1: Удалить pure-doc артефакты

**Files:**
- Delete: `docs/avito-legal.md`
- Delete: `skills/avito-legal-guardrails/` (весь каталог)
- Delete: `skills/avito-official-api/` (весь каталог)

- [ ] **Step 1: Удалить файлы**

```bash
git rm docs/avito-legal.md
git rm -r skills/avito-legal-guardrails skills/avito-official-api
```

- [ ] **Step 2: Проверить, что осталось два скила**

Run: `ls -1 skills/`
Expected: только `scraping-avito` и `using-avito-mcp`

- [ ] **Step 3: Зафиксировать входящие ссылки на удалённое (для правки в след. задачах)**

Run: `grep -rln -e "avito-legal-guardrails" -e "avito-official-api" -e "avito-legal.md" --include="*.md" --include="*.json" .`
Expected: список файлов (CLAUDE.md, docs/*, skills/*, README.md, …) — все они правятся в Task 2–6. Запиши список.

- [ ] **Step 4: Commit**

```bash
git add -A skills/ docs/
git commit -F <msg-file>
```
Сообщение: `docs: remove legal-guardrails and official-api skills + legal doc`

---

### Task 2: Переписать `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Удалить блоки текущей реализации**

Удалить/переписать:
- раздел «## Guardrails (обязательно)» — целиком;
- в «## Что это» — счётчик «4 тулзы» и перечень official-api тулз;
- в «## Переменные окружения» — строки `AVITO_CLIENT_ID`/`AVITO_CLIENT_SECRET`;
- в «## Gotchas» — пункты про `validate_endpoint`/allowlist, `get_account_info`
  ПДн-минимизацию, кэш токена официального API, `models.py` OwnItem;
- в «## Изменение MCP-сервера» — упоминания `official_api.py`, `own_items.py`.

- [ ] **Step 2: Добавить целевое описание**

Вписать по спеке:
- «## Что это» → плагин с полным фичесетом парсинга Avito; **7 тулз** (перечислить из spec §4),
  все — 🔜 план; движок валидирован живьём (spec §1).
- «## Переменные окружения» → таблица из spec §7 (`SPFA_API_KEY`,
  `AVITO_COOKIE_PROVIDER`, `AVITO_PROXY`, `AVITO_PROXY_CHANGE_URL`, TG/VK,
  `AVITO_DB_PATH`, `AVITO_MAX_ROTATE_ATTEMPTS`).
- «## Структура сервера» → раскладка модулей из spec §3
  (cookies/proxies/http/export/notifications/filters/storage/parser/tools).
- Раздел «## Документация зависимостей — Context7 (обязательно)» — **сохранить как есть**.

- [ ] **Step 3: Проверить отсутствие следов удалённого**

Run: `grep -n -e "official_api" -e "get_own_items" -e "AVITO_CLIENT" -e "validate_endpoint" -e "avito-legal-guardrails" -e "avito-official-api" CLAUDE.md`
Expected: пусто (нет совпадений)

- [ ] **Step 4: Commit**

```bash
git add -f CLAUDE.md
git commit -F <msg-file>
```
Сообщение: `docs: rewrite CLAUDE.md for parser feature-set target`

---

### Task 3: Переписать `docs/architecture.md` и `docs/mcp-server.md`

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/mcp-server.md`

- [ ] **Step 1: `docs/architecture.md`**

- в схеме и «Состав репозитория» заменить тулз-строку на движок парсинга + 7 тулз;
- добавить раздел «Структура сервера» с раскладкой модулей из spec §3;
- убрать упоминания официального API как текущего.

- [ ] **Step 2: `docs/mcp-server.md`**

- заменить таблицу «Тулзы» на 7 тулз из spec §4 (все 🔜 план), с колонкой «Назначение»;
- обновить блок «СТАТУС» под целевой дизайн;
- раздел провайдеров (куки/прокси/http) из spec §6; env из spec §7;
- убрать пример `get_listing` официального стиля → оставить парсинг-ориентированный;
- «Раздача skills по MCP» — сохранить.

- [ ] **Step 3: Проверить**

Run: `grep -n -e "official_api" -e "AVITO_CLIENT" -e "validate_endpoint" docs/architecture.md docs/mcp-server.md`
Expected: пусто

- [ ] **Step 4: Commit**

```bash
git add docs/architecture.md docs/mcp-server.md
git commit -F <msg-file>
```
Сообщение: `docs: rewrite architecture and mcp-server docs for parity`

---

### Task 4: Переписать `roadmap.md`, `skills.md`, `portability.md`, `avito-scraping.md`

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `docs/skills.md`
- Modify: `docs/portability.md`
- Modify: `docs/avito-scraping.md`

- [ ] **Step 1: `docs/roadmap.md`**

Заменить этапы на фазы из spec §11 (Фаза 0 документация … Фаза 5 доп. провайдеры).
Пометить «Линия A» (официальный API) как удалённую.

- [ ] **Step 2: `docs/skills.md`**

Обновить инвентарь: два скила (`scraping-avito`, `using-avito-mcp`). Удалить записи
`avito-legal-guardrails`, `avito-official-api`.

- [ ] **Step 3: `docs/portability.md`**

Обновить ссылки на тулзы (7 новых); убрать примеры официального API.

- [ ] **Step 4: `docs/avito-scraping.md`**

Переписать в чистую техдоку движка: spfa-куки → rotate-until-clean → follow-редирект
→ `find_json_on_page` → `catalog.items`. Убрать legal-обрамление «избегать капчу, потому
что закон» → оставить техническое «как пройти антибот». Отразить типичный дефект
наивной retry-логики (одна ротация → сдача) и наше улучшение.

- [ ] **Step 5: Проверить**

Run: `grep -rn -e "avito-legal" -e "avito-official-api" -e "official_api" docs/roadmap.md docs/skills.md docs/portability.md docs/avito-scraping.md`
Expected: пусто

- [ ] **Step 6: Commit**

```bash
git add docs/roadmap.md docs/skills.md docs/portability.md docs/avito-scraping.md
git commit -F <msg-file>
```
Сообщение: `docs: rewrite roadmap, skills, portability, scraping docs`

---

### Task 5: Переписать скилы `scraping-avito` и `using-avito-mcp`

**Files:**
- Modify: `skills/scraping-avito/SKILL.md`
- Modify: `skills/using-avito-mcp/SKILL.md`

- [ ] **Step 1: `skills/scraping-avito/SKILL.md`**

- `description` — WHEN-триггеры под движок (403/429/rotate/spfa/redirect), без «legal».
- тело — how-to: провайдер кук (spfa дефолт) → rotate-until-clean → follow-редирект
  (канонический URL с кодом категории) → `find_json_on_page` → факты.
- убрать ссылки на `avito-legal-guardrails`; «Капча — стоп-сигнал» оставить как
  техническую тактику (ротация чистых IP), без правовой аргументации.

- [ ] **Step 2: `skills/using-avito-mcp/SKILL.md`**

- таблица тулз → 7 из spec §4 (статусы 🔜 план);
- убрать раздел «свои объявления → официальный API» и ссылку на `avito-official-api`;
- «Related» — только `scraping-avito`.

- [ ] **Step 3: Проверить**

Run: `grep -rn -e "avito-legal-guardrails" -e "avito-official-api" -e "official_api" skills/`
Expected: пусто

- [ ] **Step 4: Commit**

```bash
git add skills/scraping-avito/SKILL.md skills/using-avito-mcp/SKILL.md
git commit -F <msg-file>
```
Сообщение: `docs(skills): rewrite scraping-avito and using-avito-mcp`

---

### Task 6: Обновить манифесты и `.env.example`

**Files:**
- Modify: `.env.example`
- Modify: `.mcp.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `gemini-extension.json`
- Modify: `.cursor-plugin/plugin.json`

- [ ] **Step 1: `.env.example`**

Удалить `AVITO_CLIENT_ID`/`AVITO_CLIENT_SECRET`. Добавить переменные из spec §7
(`SPFA_API_KEY`, `AVITO_COOKIE_PROVIDER`, `AVITO_OWN_COOKIES`, `AVITO_PROXY`,
`AVITO_PROXY_CHANGE_URL`, TG/VK, `AVITO_DB_PATH`, `AVITO_MAX_ROTATE_ATTEMPTS`) с
комментариями. `LOG_LEVEL` оставить (пометка «пока не читается»).

- [ ] **Step 2: `.mcp.json`**

В блоке `env` (если есть) заменить official-API переменные на новые. Команда запуска
не меняется.

- [ ] **Step 3: descriptions в манифестах**

Обновить `description` в `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `gemini-extension.json`,
`.cursor-plugin/plugin.json` под новый фичесет (парсинг/мониторинг Avito, а не
официальный API). **Версии (`version`) не трогать** — бамп в Фазе 1.

- [ ] **Step 4: Проверить синхронность версий**

Run: `python3 scripts/check_versions.py`
Expected: exit 0 (версии синхронны — мы их не меняли)

- [ ] **Step 5: Валидация плагина**

Run: `claude plugin validate ./`
Expected: PASS (допустим 1 known minor warning про CLAUDE.md)

- [ ] **Step 6: Commit**

```bash
git add .env.example .mcp.json .claude-plugin/plugin.json .claude-plugin/marketplace.json gemini-extension.json .cursor-plugin/plugin.json
git commit -F <msg-file>
```
Сообщение: `docs: update manifests and .env.example for parity target`

---

### Task 7: Финальная сверка консистентности

**Files:** — (проверки, без правок; если что-то всплывёт — точечная правка + коммит)

- [ ] **Step 1: Нет следов удалённого во всём репо (кроме spec и plans)**

Run: `grep -rln -e "official_api_call" -e "get_own_items" -e "get_account_info" -e "avito-legal-guardrails" -e "avito-official-api" -e "AVITO_CLIENT_ID" --include="*.md" --include="*.json" . | grep -v "docs/superpowers/"`
Expected: пусто (совпадения только в spec/plans — это ожидаемо)

- [ ] **Step 2: README.md, AGENTS.md, GEMINI.md переписаны**

Проверить, что верхнеуровневые доки не описывают официальный API как текущий.
Run: `grep -ln -e "official" -e "get_own_items" README.md AGENTS.md GEMINI.md`
Expected: пусто (либо только исторические пометки). Если есть — переписать и закоммитить.

- [ ] **Step 3: Версии + валидация ещё раз**

Run: `python3 scripts/check_versions.py && claude plugin validate ./`
Expected: check_versions exit 0; validate PASS.

- [ ] **Step 4: Финальный статус git**

Run: `git log --oneline main..HEAD`
Expected: серия атомарных docs-коммитов Фазы 0.

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки:** §2 (удаления) → Task 1; §3 (структура) → Task 2,3; §4 (тулзы) →
  Task 2,3,5; §6 (провайдеры) → Task 3; §7 (env) → Task 2,3,6; §9 (доки) → Task 2–6;
  §11 (фазы→roadmap) → Task 4. README/AGENTS/GEMINI → Task 7 Step 2.
- **Плейсхолдеры:** нет; содержание берётся из спеки по ссылке (DRY).
- **Консистентность:** список тулз/env/структура — единый источник (spec). Имена
  удаляемого совпадают между Task 1 (удаление) и Task 7 (grep-сверка).
```
