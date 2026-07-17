# avito-mcp-plugin

Переносимый плагин для AI-агентов (Claude Code, Cursor, Codex, Gemini CLI и др.)
для работы с [Avito](https://avito.ru): набор **skills** + встроенный
**MCP-сервер** на Python ([FastMCP v3](https://gofastmcp.com)).

> **СТАТУС: ранняя разработка (v0.1.0).** Готовы документация, каркас плагина и
> первый рабочий слой MCP-сервера (официальный API, модели, утилиты — 26 тестов).
> Парсинг-тулзы и финализация skills — впереди, см. [`docs/roadmap.md`](docs/roadmap.md).

## Идея

Плагин построен по принципу **«толстое ядро + тонкие адаптеры»**:

- **MCP-сервер** несёт детерминированную логику (HTTP к Avito, парсинг,
  официальный API) — код тулз не попадает в контекст агента.
- **Skills** несут процедурное знание: как обходить антибот, что можно собирать
  по закону, как работать с официальным API.
- **Тонкие адаптеры** (`AGENTS.md`, `GEMINI.md`, …) дают переносимость между
  агентами.

Подробнее — [`docs/architecture.md`](docs/architecture.md).

## Что внутри

### Skills

| Скил | Когда триггерится |
|---|---|
| [`using-avito-mcp`](skills/using-avito-mcp/SKILL.md) | нужны данные Avito → маршрутизация в тулзы |
| [`scraping-avito`](skills/scraping-avito/SKILL.md) | антибот, `403`/`429`, капча при парсинге |
| [`avito-legal-guardrails`](skills/avito-legal-guardrails/SKILL.md) | перед сбором/хранением данных |
| [`avito-official-api`](skills/avito-official-api/SKILL.md) | работа со своими объявлениями через API |

### MCP-сервер

Пакет [`avito-mcp-server`](server/README.md) на FastMCP v3. Реализованы тулза
`ping`, клиент официального API и тулза `official_api_call` (свои объявления),
доменные модели и утилиты. Парсинг-тулзы (`search_listings`, `get_listing`) —
в разработке.

## Установка

> Плагин ещё не опубликован в маркетплейсе. Пока — локальная установка для разработки.

### Claude Code (локально)

```bash
git clone https://github.com/evgenygurin/avito-mcp-plugin.git
claude --plugin-dir ./avito-mcp-plugin     # загрузить на сессию
# внутри Claude Code:
/reload-plugins
claude plugin validate ./avito-mcp-plugin  # проверка манифеста
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
- [Право (РФ)](docs/avito-legal.md) — ст. 1334 ГК, 152-ФЗ, ст. 272 УК
- [Переносимость](docs/portability.md) — конфиги MCP по агентам
- [Roadmap](docs/roadmap.md) — этапы разработки
- [Исследования](docs/researches/) — первичные research-материалы

## Философия

- **Детерминизм в тулзах, знание в skills** — тяжёлая логика не ест контекст.
- **Переносимость** — открытые стандарты (MCP, Agent Skills), не привязка к рантайму.
- **Guardrails первыми** — правовые ограничения РФ явно, до сбора данных.
- **Documentation TDD** — skills тестируются на свежих агентах до релиза.

## Дисклеймер

Парсинг Avito несёт правовые риски в РФ (смежное право на БД, ПДн, обход
техсредств защиты). См. [`docs/avito-legal.md`](docs/avito-legal.md). Материалы
репозитория носят справочный характер и не являются юридической консультацией.

## Вклад

См. [`CONTRIBUTING.md`](CONTRIBUTING.md). Skills создаются и меняются по
методологии `superpowers:writing-skills`.

## Лицензия

MIT (файл `LICENSE` будет добавлен на этапе публикации — см. roadmap).
