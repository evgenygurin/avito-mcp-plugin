# Архитектура

`avito-mcp-plugin` построен по принципу **«толстое ядро + тонкие адаптеры»**:
детерминированная логика живёт в MCP-серверах, процедурное знание — в skills,
а переносимость между агентами обеспечивают тонкие адаптеры. После рефакторинга
(Фазы 1–5, см. [`roadmap.md`](roadmap.md)) монолит разбит на **ролевые серверы**,
а gateway — единая «входная дверь».

## Два переносимых слоя

| Слой | Что несёт | Формат | Переносимость |
|---|---|---|---|
| **MCP-серверы** | детерминированные операции, side-effects, доступ к API/БД | Python / FastMCP v3 | один gateway — все агенты |
| **Skills** | процедурное знание, «как думать», workflow, паттерны | `SKILL.md` (agentskills.io) | открытый стандарт |

Ключевая идея: **skill ссылается на тулзу словами-действиями, а не по имени
рантайма** — это делает и skill, и связку переносимыми.

## Распределённая композиция

Логика разнесена по ролевым серверам (образец — dj-music
[`ARCHITECTURE.md`](https://github.com/evgenygurin/dj-music-mcp/blob/main/docs/ARCHITECTURE.md)):

```text
                    ┌─────────────────────────────────────────────────┐
  AI-агент ────────▶│  gateway (avito-mcp-server)                входная │
  (Claude, Cursor,  │  7 MCP-тулз + skills по MCP + прокси db/notify │
   Codex, Gemini…)  └───────┬───────────────┬───────────────┬────────┘
                           │ импорт         │ импорт         │ импорт
             ┌─────────────▼─────┐  ┌───────▼────────┐  ┌─────▼─────────┐
             │ scraper (stateless)│  │ db (stateful)  │  │ notify        │
             │ движок парсинга    │  │ Supabase/экспорт│  │ Telegram/VK   │
             └────────────────────┘  └────────────────┘  └───────────────┘
```

- **gateway** — «входная дверь»: регистрирует на себе тулзы scraper/db/notify
  **импортом** (`register(gw)`), что даёт исходные имена и общий `Context`
  без IPC-оверхеда; дополнительно монтирует скелеты db/notify как прокси
  (`create_proxy` + `mount`) под неймспейсами `db_*`, `notify_*`.
  Раздаёт `skills/` по MCP (`SkillsProvider`).
- **scraper** — движок парсинга (stateless): провайдеры кук/прокси,
  rotate-until-clean, `curl_cffi`, извлечение JSON каталога, фильтры.
- **db** — единственный stateful: знает про Supabase (`AVITO_SUPABASE_DSN`),
  dedup/история цены/экспорт (`record_scan_result`, `get_price_history`,
  `export_listings`).
- **notify** — уведомления Telegram/VK (`send_notification`).
- **shared** — общие утилиты: `ServerRole`, `ROLE_NAMESPACES` (источник правды
  для неймспейсов композиции).

## Как соединяются серверы

Ключевое решение — **без лишнего IPC**: тяжёлые серверы (scraper/db/notify)
не монтируются как `mcp`-прокси в единственную строку клиента; их тулзы
регистрируются в gateway **импортом**, поэтому:

- у тулз исходные имена (`search_listings`, а не `scraper_search_listings`);
- общий `Context` и аннотации сохраняются;
- нет JSON-RPC-обвязки между gateway и ролевыми серверами.

Дополнительно скелеты db/notify монтируются через
`create_proxy` + `gw.mount(..., namespace=ROLE_NAMESPACES[role])`, чтобы
внешний клиент видел и неймспейсные `db_status`, `notify_status`,
`notify_send_notification`.

### Стыковка «scan → db» (ToolTransform)

Gateway-тулза `scan_new_listings` собирает каталог через scraper-движок и
**отдаёт сырой результат на персистент в db** — чистой функцией
`persist_scan` (импорт из db), без IPC. В db этот контракт наружу — тулза
`record_scan_result` (внутренняя) и `get_price_history`/`export_listings`
(внешние, доступны и в gateway).

## Когда что использовать

| Механизм | Для чего | Где |
|---|---|---|
| **MCP tool** | детерминированные операции, side-effects, доступ к БД/API | `servers/*` |
| **Skill** | процедурное знание, workflow, паттерны | `skills/` |
| **Command** | явный слэш-триггер (`/…`) | `commands/` (пока нет) |
| **Subagent** | изолированный контекст под задачу | `agents/` (пока нет) |
| **Hook** | реакция на события (SessionStart, PostToolUse) | `hooks/` (пока нет) |

**Правило:** если что-то добивается валидацией/регуляркой — автоматизируй
(tool/hook); документацию оставляй для суждений (skill). Тяжёлую логику **не**
клади в skills — она ест контекст.

## Состав репозитория

```text
avito-mcp-plugin/
├── .claude-plugin/plugin.json      # манифест плагина (только он в .claude-plugin/)
├── .claude-plugin/marketplace.json # запись маркетплейса
├── .mcp.json                        # единая точка входа — gateway (ниже)
├── gemini-extension.json           # адаптер Gemini CLI
├── servers/                        # uv-workspace ролевых серверов
│   ├── gateway/ scraper/ db/ notify/ shared/
│   └── uv.lock                     # общий замок зависимостей
├── skills/                         # 2 скила (scraping-avito, using-avito-mcp)
├── docs/                           # эта документация
├── README.md · CLAUDE.md · AGENTS.md · GEMINI.md · CONTRIBUTING.md
```

Каноническое правило Claude Code: **только `plugin.json` лежит в
`.claude-plugin/`**; остальное (`skills/`, `.mcp.json`, …) — в корне плагина.
Если положить `skills/` внутрь `.claude-plugin/`, они станут невидимы.

## Единая точка входа: `.mcp.json`

Клиент запускает **только gateway**; ролевые серверы подтягиваются им как
Python-пакеты uv-workspace (`servers/`), поэтому отдельная конфигурация
внешнему клиенту не нужна:

```jsonc
{
  "avito": {
    "command": "uv",
    "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/servers/gateway", "avito-mcp-server"],
    "env": { "LOG_LEVEL": "info", "UV_PROJECT_ENVIRONMENT": "${CLAUDE_PLUGIN_DATA}/venv" }
  }
}
```

## 7 MCP-тулз (реализованы)

Через gateway доступны все 7 тулз под исходными именами; каждую — подробнее в
[`mcp-server.md`](mcp-server.md).

| # | Тулза | Владелец | Назначение |
|---|---|---|---|
| 1 | `search_listings` | scraper | поиск каталога (фильтры, `pages`) |
| 2 | `get_listing` | scraper | детали объявления |
| 3 | `check_proxy_health` | scraper | диагностика прокси/ротации |
| 4 | `scan_new_listings` | gateway+scraper+db | dedup + отслеживание цены |
| 5 | `get_price_history` | db | история цены из Postgres |
| 6 | `export_listings` | db | xlsx / json / csv |
| 7 | `send_notification` | notify | Telegram / VK |

Плюс неймспейсные прокси db/notify: `db_status`, `notify_status`,
`notify_send_notification`.

## Версионирование

SemVer синхронно в **пяти** манифестах:

- `.claude-plugin/plugin.json` — `version` (кэш-ключ обновления Claude Code);
- `.claude-plugin/marketplace.json` — запись маркетплейса;
- `servers/gateway/pyproject.toml` — версия пакета для PyPI;
- `gemini-extension.json` — адаптер Gemini CLI;
- `.cursor-plugin/plugin.json` — адаптер Cursor.

При бампе меняй все пять: `python3 scripts/check_versions.py` (exit 0 =
совпадают). FastMCP не версионирует тулзы автоматически: при breaking-изменении
сигнатуры тулзы звони major или используй `@tool(version=...)`.

## Дальше

- Как устроены skills → [`skills.md`](skills.md)
- Как запускать серверы по отдельности → [`mcp-server.md`](mcp-server.md)
- Переносимость между агентами → [`portability.md`](portability.md)
- Статус фаз и плана → [`roadmap.md`](roadmap.md)