# Архитектура

`avito-mcp-plugin` построен по принципу **«толстое ядро + тонкие адаптеры»**:
детерминированная логика живёт в MCP-сервере, процедурное знание — в skills,
а переносимость между агентами обеспечивают тонкие адаптеры.

## Два переносимых слоя

| Слой | Что несёт | Формат | Переносимость |
|---|---|---|---|
| **MCP-сервер** | Детерминированные операции, side-effects, доступ к API/БД | Python / FastMCP v3 | один сервер — все агенты, различаются лишь конфиги |
| **Skills** | Процедурное знание, «как думать», workflow, паттерны | `SKILL.md` (agentskills.io) | открытый стандарт, десятки инструментов |

Ключевая идея: **skill ссылается на тулзу словами-действиями, а не по имени
рантайма**. Это делает и skill, и связку переносимыми.

## Схема

```text
                    ┌──────────────────────────────┐
   AI-агент ───────▶│  skills/*  (SKILL.md)         │  процедурное знание,
   (Claude Code,    │  scraping-avito / using-avito │  «как думать», workflow
    Cursor, Codex,  └──────────────┬───────────────┘
    Gemini CLI …)                  │ вызывает словами-действиями
                                   ▼
                    ┌──────────────────────────────┐
                    │  MCP-сервер `avito` (FastMCP) │  движок парсинга:
                    │  7 тулз: search / get / scan… │  куки → rotate-until-clean
                    └──────────────┬───────────────┘  → curl_cffi → извлечение JSON
                                   ▼
                    Avito: HTML-каталог (loaderData.data.catalog) + SSR-редирект
```

## Когда что использовать

| Механизм | Для чего | Где |
|---|---|---|
| **MCP tool** | Детерминированные операции, side-effects, доступ к БД/API. Код НЕ входит в контекст. | `server/` |
| **Skill** | Процедурное знание, workflow, паттерны. Инжектится в контекст при триггере. | `skills/` |
| **Command** | Явный слэш-триггер пользователя (`/…`). | `commands/` (пока нет) |
| **Subagent** | Изолированный контекст под задачу (review, explore). | `agents/` (пока нет) |
| **Hook** | Реакция на события (SessionStart, PostToolUse). | `hooks/` (пока нет) |

**Правило:** если что-то enforce-ится валидацией/регуляркой — автоматизируй
(tool/hook); документацию оставляй для суждений (skill). Тяжёлую логику **не**
клади в skills — она ест контекст.

## Состав репозитория

```text
avito-mcp-plugin/
├── .claude-plugin/plugin.json      # манифест плагина (только он лежит здесь)
├── .claude-plugin/marketplace.json # запись маркетплейса
├── .mcp.json                       # объявление MCP-сервера (плоский формат)
├── gemini-extension.json           # адаптер Gemini CLI
├── skills/                         # 2 скила (scraping-avito, using-avito-mcp)
├── server/                         # Python-пакет MCP-сервера — движок парсинга (src-layout)
├── docs/                           # эта документация
├── README.md · CLAUDE.md · AGENTS.md · GEMINI.md · CONTRIBUTING.md
```

Каноническое правило Claude Code: **только `plugin.json` лежит в
`.claude-plugin/`**; все компоненты (`skills/`, `.mcp.json`, …) — в корне
плагина. Если положить `skills/` внутрь `.claude-plugin/`, они станут невидимы
(тихий провал).

## Структура сервера

Ядро MCP несёт **собственный движок парсинга** — полнофункциональный парсер
каталога Avito: внутренняя раскладка `server/src/avito_mcp_server/` разложена
по функциональным модулям (куки, прокси, HTTP-клиент, экспорт, уведомления,
фильтры, хранилище).

```text
avito_mcp_server/
├── cookies/            # провайдеры кук: spfa (дефолт) / own / playwright
├── proxies/            # Mobile / Server / None + ротация-до-чистого
├── http/               # curl_cffi клиент (impersonate, retry)
├── export/             # xlsx / json / csv
├── notifications/      # Telegram, VK
├── filters/            # keyword / seller / price / geo / max_age
├── storage/            # Postgres (Supabase), SQLAlchemy ORM: dedup + история цены + cooldown
│                       #   base.py — Protocol'ы ListingStore / ProxyCooldownStore (DIP)
├── models.py           # Listing / SearchResult (факты + опции)
├── parser/             # ядро: state.py (SSR-JSON + PageKind) / mapping.py (→ Listing)
│                       #   / pagination.py (обход); импорт — через фасад parser/
├── skills_provider.py  # раздача skills по MCP
├── tools/              # тонкий MCP-слой поверх ядра (register(mcp) на группу)
│                       #   catalog.py — общий обход каталога, execution.py — поток + ToolError
└── server.py           # инстанс + main() + регистрация групп тулз
```

**Движок** (валидирован живьём): провайдер кук → **rotate-until-clean** (ротация
IP до чистого) → curl_cffi (`impersonate`) + follow SSR-редиректа на канонический
URL категории → `find_json_on_page` (`script[type=mime/invalid][data-mfe-state=true]`)
→ `loaderData.data.catalog.items`. Наше улучшение retry-логики: rotate-until-clean
вместо одной ротации — устраняет типичный дефект наивной retry-логики (одна
ротация → сдача).

### 7 MCP-тулз (реализованы)

Фильтры — параметры тулз, не отдельные тулзы; держит нас под
лимитом Anthropic «< 20 тулз». Код ещё **не написан**.

| # | Тулза | Назначение |
|---|---|---|
| 1 | `search_listings` | поиск каталога (фильтры и `pages` — параметры) |
| 2 | `get_listing` | детали объявления по `id_or_url` |
| 3 | `scan_new_listings` | dedup + отслеживание цены (мониторинг-примитив, Postgres) |
| 4 | `check_proxy_health` | диагностика прокси/ротации |
| 5 | `send_notification` | Telegram / VK |
| 6 | `export_listings` | xlsx / json / csv |
| 7 | `get_price_history` | история цены из Postgres |

Возврат — Pydantic-модели (structured output). Ошибки наружу — через `ToolError`.
План реализации по фазам — в [`roadmap.md`](roadmap.md).

## Версионирование

SemVer синхронно в **пяти** манифестах:

- `.claude-plugin/plugin.json` → `version` — кэш-ключ обновления для Claude Code;
- `.claude-plugin/marketplace.json` → `version` — запись маркетплейса;
- `server/pyproject.toml` → `version` — версия пакета для PyPI;
- `gemini-extension.json` → `version` — адаптер Gemini CLI;
- `.cursor-plugin/plugin.json` → `version` — адаптер Cursor.

При бампе меняй все пять и проверяй синхронность:
`python3 scripts/check_versions.py` (exit 0 = совпадают). FastMCP не версионирует
тулзы автоматически: при breaking-изменении сигнатуры тулзы бампай major или
используй `@tool(version=...)`.

## Дальше

- Как устроены skills → [`skills.md`](skills.md)
- Как устроен MCP-сервер → [`mcp-server.md`](mcp-server.md)
- Переносимость между агентами → [`portability.md`](portability.md)
- План развития → [`roadmap.md`](roadmap.md)
