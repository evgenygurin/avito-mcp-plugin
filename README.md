# avito-mcp-plugin

Переносимый плагин для AI-агентов (Claude Code, Cursor, Codex, Gemini CLI и др.)
для работы с [Avito](https://avito.ru): набор **skills** + встроенный
**MCP-сервер** на Python ([FastMCP v3](https://gofastmcp.com)).

> **СТАТУС: ранняя разработка (v0.1.0).** Цель — **полнофункциональный парсер
> каталога Avito**: парсинг и мониторинг публичных объявлений Avito. Движок
> (куки → rotate-until-clean → curl_cffi → извлечение JSON каталога) и **все 7
> MCP-тулз реализованы**. Сетевую часть не проверить без чистого RU-прокси:
> с домашнего IP Avito отдаёт 403/429 после 2–3 запросов. План —
> [`docs/roadmap.md`](docs/roadmap.md), канон —
> [дизайн парсера Avito](docs/superpowers/specs/2026-07-18-avito-parser-design.md).

## Идея

Плагин построен по принципу **«толстое ядро + тонкие адаптеры»**:

- **MCP-сервер** несёт детерминированную логику движка парсинга (куки, прокси,
  rotate-until-clean, HTTP на `curl_cffi`, извлечение JSON, фильтры, Postgres (Supabase),
  экспорт, уведомления) — код тулз не попадает в контекст агента.
- **Skills** несут процедурное знание: как обходить антибот (rotate-until-clean,
  чистые RU-прокси) и как выбирать нужную MCP-тулзу под задачу.
- **Тонкие адаптеры** (`AGENTS.md`, `GEMINI.md`, …) дают переносимость между
  агентами.

Подробнее — [`docs/architecture.md`](docs/architecture.md).

## Что внутри

### Skills

| Скил | Когда триггерится |
|---|---|
| [`using-avito-mcp`](skills/using-avito-mcp/SKILL.md) | нужны данные Avito → маршрутизация в тулзы |
| [`scraping-avito`](skills/scraping-avito/SKILL.md) | антибот, `403`/`429`, капча при парсинге |

Полный статус скилов — [`docs/skills.md`](docs/skills.md).

### MCP-сервер

Пакет [`avito-mcp-server`](server/README.md) на FastMCP v3 — несёт движок
парсинга: провайдер кук (spfa) → rotate-until-clean → curl_cffi
(`impersonate`) + follow SSR-редиректа → извлечение `loaderData.data.catalog.items`.
Движок валидирован живьём и портирован в код; **7 MCP-тулз** (`search_listings`,
`get_listing`, `scan_new_listings`, `check_proxy_health`, `send_notification`,
`export_listings`, `get_price_history`) работают. Состояние (dedup, история цены,
cooldown прокси) — в Postgres проекта Supabase (`AVITO_SUPABASE_DSN`). Раздача
`skills/` по MCP (`SkillsProvider`) работает.

## Установка

> Плагин ещё не опубликован в маркетплейсе. Пока — локальная установка для разработки.

### Claude Code (локально)

```bash
git clone https://github.com/evgenygurin/avito-mcp-plugin.git
claude --plugin-dir ./avito-mcp-plugin     # загрузить на сессию
# внутри Claude Code:
/reload-plugins
claude plugin validate ./avito-mcp-plugin --strict  # проверка манифестов (не скилов)
```

MCP-сервер стартует автоматически (см. [`.mcp.json`](.mcp.json)); требуется
установленный [`uv`](https://docs.astral.sh/uv/).

### Другие агенты

Готовые конфиги MCP-сервера для Cursor / Codex / Gemini CLI / VS Code —
[`examples/mcp-configs/`](examples/mcp-configs/); тонкие адаптеры —
[`.cursor-plugin/`](.cursor-plugin/plugin.json) и [`.codex/INSTALL.md`](.codex/INSTALL.md).
Форматы и нюансы — [`docs/portability.md`](docs/portability.md).

Сервер также **раздаёт skills по MCP** (`skill://<name>/SKILL.md`) — любой
MCP-клиент получает их через `list_resources`/`read_resource`.

## Документация

- [Архитектура](docs/architecture.md) — ядро + адаптеры, когда skill/tool/command/hook
- [Skills](docs/skills.md) — стандарт agentskills.io, progressive disclosure
- [MCP-сервер](docs/mcp-server.md) — FastMCP v3, тулзы, тесты, дистрибуция
- [Парсинг Avito](docs/avito-scraping.md) — антибот, гибридная схема, прокси
- [Дизайн парсера Avito](docs/superpowers/specs/2026-07-18-avito-parser-design.md) — канон: движок, 7 тулз, фазы
- [Переносимость](docs/portability.md) — конфиги MCP по агентам
- [Релиз](docs/releasing.md) — версии, сборка, публикация в PyPI
- [Roadmap](docs/roadmap.md) — этапы разработки
- [Исследования](docs/researches/) — первичные research-материалы

## Философия

- **Детерминизм в тулзах, знание в skills** — тяжёлая логика не ест контекст.
- **Переносимость** — открытые стандарты (MCP, Agent Skills), не привязка к рантайму.
- **Полнофункциональный парсер каталога Avito** — фактические данные и мониторинг публичных объявлений;
  `parse_phone` (сбор телефонов продавцов) сознательно не реализуется — ПДн
  третьих лиц.
- **Documentation TDD** — skills тестируются на свежих агентах до релиза.

## Дисклеймер

Парсинг публичных объявлений Avito сопряжён с правовыми рисками в РФ (антибот,
смежное право на БД, ПДн при выходе за фактические поля). Проект не даёт
юридических консультаций и не документирует это как отдельную guardrails-фичу —
риски использования несёт оператор. Материалы репозитория носят справочный
характер.

## Вклад

См. [`CONTRIBUTING.md`](CONTRIBUTING.md). Skills создаются и меняются по
методологии `superpowers:writing-skills`.

## Лицензия

MIT — см. [`LICENSE`](LICENSE).
