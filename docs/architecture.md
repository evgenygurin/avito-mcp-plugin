# Архитектура

`avito-mcp-plugin` построен по принципу **«толстое ядро + тонкие адаптеры»**:
детерминированная логика живёт в MCP-сервере, процедурное знание — в skills,
а переносимость между агентами обеспечивают тонкие адаптеры.

## Два переносимых слоя

| Слой | Что несёт | Формат | Переносимость |
|---|---|---|---|
| **MCP-сервер** | Детерминированные операции, side-effects, доступ к API/БД | Python / FastMCP v3 | один сервер — все агенты, различаются лишь конфиги |
| **Skills** | Процедурное знание, «как думать», workflow, guardrails | `SKILL.md` (agentskills.io) | открытый стандарт, десятки инструментов |

Ключевая идея: **skill ссылается на тулзу словами-действиями, а не по имени
рантайма**. Это делает и skill, и связку переносимыми.

## Схема

```text
                    ┌──────────────────────────────┐
   AI-агент ───────▶│  skills/*  (SKILL.md)         │  процедурное знание,
   (Claude Code,    │  scraping / legal / api / use │  guardrails, «как думать»
    Cursor, Codex,  └──────────────┬───────────────┘
    Gemini CLI …)                  │ вызывает словами-действиями
                                   ▼
                    ┌──────────────────────────────┐
                    │  MCP-сервер `avito` (FastMCP) │  детерминизм: HTTP, парсинг,
                    │  tools: search / get / api …  │  официальный API, прокси
                    └──────────────┬───────────────┘
                                   ▼
                    Avito: m.avito.ru/api/* · api.avito.ru · HTML
```

## Когда что использовать

| Механизм | Для чего | Где |
|---|---|---|
| **MCP tool** | Детерминированные операции, side-effects, доступ к БД/API. Код НЕ входит в контекст. | `server/` |
| **Skill** | Процедурное знание, workflow, паттерны, guardrails. Инжектится в контекст при триггере. | `skills/` |
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
├── skills/                         # 4 skeleton-скила
├── server/                         # Python-пакет MCP-сервера (src-layout)
├── docs/                           # эта документация
├── README.md · CLAUDE.md · AGENTS.md · GEMINI.md · CONTRIBUTING.md
```

Каноническое правило Claude Code: **только `plugin.json` лежит в
`.claude-plugin/`**; все компоненты (`skills/`, `.mcp.json`, …) — в корне
плагина. Если положить `skills/` внутрь `.claude-plugin/`, они станут невидимы
(тихий провал).

## Версионирование

SemVer синхронно в двух местах:

- `.claude-plugin/plugin.json` → `version` — кэш-ключ обновления для Claude Code;
- `server/pyproject.toml` → `version` — версия пакета для PyPI.

Держи их синхронно (в идеале — CI-bump). FastMCP не версионирует тулзы
автоматически: при breaking-изменении сигнатуры тулзы бампай major или используй
`@tool(version=...)`.

## Дальше

- Как устроены skills → [`skills.md`](skills.md)
- Как устроен MCP-сервер → [`mcp-server.md`](mcp-server.md)
- Переносимость между агентами → [`portability.md`](portability.md)
- План развития → [`roadmap.md`](roadmap.md)
