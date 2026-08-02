# avito-mcp-plugin

Переносимый плагин для AI-агентов (Claude Code, Cursor, Codex, Gemini CLI и др.)
для работы с [Avito](https://avito.ru): набор **skills** + **MCP-серверы** на
Python ([FastMCP v3](https://gofastmcp.com)).

> **СТАТУС: v0.5.0.** Цель — **полнофункциональный парсер каталога Avito**:
> парсинг, мониторинг, история цены, экспорт и уведомления. Движок
> (куки → rotate-until-clean → curl_cffi → извлечение JSON) и **все 7 MCP-тулз
> реализованы**; после Фаз 2–5 архитектура распределена на ролевые серверы
> (`servers/`), gateway — единая точка входа. Сетевую часть не проверить без
> чистого RU-прокси: с домашнего IP Avito отдаёт 403/429 после 2–3 запросов.
> План и статус фаз — [`docs/roadmap.md`](docs/roadmap.md).

## Идея

Плагин построен по принципу **«толстое ядро + тонкие адаптеры»**:

- **MCP-серверы несут** детерминированную логику (куки, прокси, rotate-until-clean,
  HTTP, извлечение JSON, фильтры, Postgres/Supabase, экспорт, уведомления);
  код тулз не попадает в контекст агента.
- **Skills** несут процедурное знание: как обходить антибот и как выбирать нужную
  MCP-тулзу под задачу.
- **Тонкие адаптеры** (`AGENTS.md`, `GEMINI.md`, …) дают переносимость между
  агентами.

Подробнее — [`docs/architecture.md`](docs/architecture.md).

## Архитектура: gateway + ролевые серверы

Монолит разбит на uv-workspace [**`servers/`**](servers/README.md) (Фазы 1–5):

| Сервер | Пакет | Роль |
|---|---|---|
| **gateway** | `avito_mcp_server` | входная дверь: 7 тулз + skills/ по MCP + прокси db/notify |
| **scraper** | `avito_mcp_scraper` | движок парсинга (stateless) |
| **db** | `avito_mcp_db` | единственный stateful: Supabase, история цен, экспорт |
| **notify** | `avito_mcp_notify` | уведомления Telegram/VK |
| **shared** | `avito_mcp_shared` | общие утилиты (роли, неймспейсы) |

Gateway — «входная дверь»: клиенты запускают только его, ролевые серверы
подтягиваются как Python-пакеты uv-workspace. **7 MCP-тулз**
(`search_listings`, `get_listing`, `scan_new_listings`, `check_proxy_health`,
`send_notification`, `export_listings`, `get_price_history`) доступны под
своими именами; состояние — в db (Supabase, `AVITO_SUPABASE_DSN`); раздача
`skills/` по MCP (`SkillsProvider`) работает.

## Skills

| Скил | Когда триггерится |
|---|---|
| [`using-avito-mcp`](skills/using-avito-mcp/SKILL.md) | нужны данные Avito → маршрутизация в тулзы |
| [`scraping-avito`](skills/scraping-avito/SKILL.md) | антибот, `403`/`429`, капча при парсинге |

Полный статус скилов — [`docs/skills.md`](docs/skills.md).

## Установка

> Плагин ещё не опубликован в маркетплейсе. Пока — локальная установка для разработки.

### Claude Code (локально)

```bash
git clone https://github.com/evgenygurin/avito-mcp-plugin.git
claude --plugin-dir ./avito-mcp-plugin     # загрузить на сессию
/reload-plugins
claude plugin validate ./avito-mcp-plugin --strict  # проверка манифестов (не скилов)
```

MCP-сервер (gateway) стартует автоматически (см. [`.mcp.json`](.mcp.json));
требуется установленный [`uv`](https://docs.astral.sh/uv/).

### Другие агенты

Готовые конфиги MCP-сервера для Cursor / Codex / Gemini CLI / VS Code —
[`examples/mcp-configs/`](examples/mcp-configs/); тонкие адаптеры —
[`.cursor-plugin/plugin.json`](.cursor-plugin/plugin.json) и
[`.codex/INSTALL.md`](.codex/INSTALL.md). Форматы и нюансы —
[`docs/portability.md`](docs/portability.md).

Сервер также **раздаёт skills по MCP** (`skill://<name>/SKILL.md`).

## Документация

- [Архитектура](docs/architecture.md) — распределённая композиция gateway + роли
- [MCP-серверы](docs/mcp-server.md) — 4 сервера, как запускать каждый отдельно
- [Skills](docs/skills.md) — стандарт agentskills.io
- [Парсинг Avito](docs/avito-scraping.md) — антибот, гибридная схема, прокси
- [Переносимость](docs/portability.md) — конфиги MCP по агентам
- [Релиз](docs/releasing.md) — версии, сборка, PyPI
- [Roadmap](docs/roadmap.md) — этапы разработки и статус рефакторинга
- [Дизайн парсера](docs/superpowers/specs/2026-07-18-avito-parser-design.md) — канон

## Философия

- **Детерминизм в тулзах, знание в skills** — тяжёлая логика не ест контекст.
- **Переносимость** — открытые стандарты (MCP, Agent Skills), а не привязка к рантайму.
- **Полнофункциональный парсер каталога Avito** — фактические данные и мониторинг
  публичных объявлений; `parse_phone` сознательно не реализуется (ПДн третьих лиц).
- **Documentation TDD** — skills тестируются на свежих агентах до релиза.

## Disclaimer

Парсинг публичных объявлений Avito сопряжён с правовыми рисками в РФ (антибот,
смежное право на БД, ПДн при выходе за фактические поля). Проект не даёт
юридических консультаций; риски несёт оператор.

## Вклад

См. [`CONTRIBUTING.md`](CONTRIBUTING.md). Skills создаются по методологии
`superpowers:writing-skills`.

## Лицензия

MIT — см. [`LICENSE`](LICENSE).