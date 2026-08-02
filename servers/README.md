# avito-mcp-servers

Распределённый набор MCP-серверов плагина [`avito-mcp-plugin`](../README.md).
**Фаза 3:** движок парсинга — в scraper (stateless), хранилище/экспорт/история
цены — в db (единственный stateful-сервер, знает про Supabase), уведомления
остаются в gateway до Фазы 4. Композиция «gateway + ролевые серверы» по образцу
[dj-music](https://github.com/evgenygurin/dj-music-mcp/blob/main/docs/ARCHITECTURE.md):
`mount` + `create_proxy`, общий контекст — импортом тулз scraper/db в gateway.

```text
servers/
├── pyproject.toml            # uv-workspace: члены gateway/scraper/db/notify/shared
├── gateway/ + avito_mcp_server  # «входная дверь»: движок + оркестрация + уведомления
├── scraper/ + avito_mcp_scraper # движок парсинга (stateless): search/get_listing/check
├── db/     + avito_mcp_db       # единственный stateful-сервер: Supabase, история, экспорт
├── notify/ + avito_mcp_notify   # скелет: уведомления (логика — фаза 4)
└── shared/ + avito_mcp_shared   # общие утилиты (роли, неймспейсы композиции)
```

## Роли

| Пакет | Роль | Неймспейс gateway | Стадия |
|---|---|---|---|
| `avito_mcp_server` (gateway) | движок (импорт) + `scan_new_listings` + уведомления + `mount`+`create_proxy` | — | Фаза 3 |
| `avito_mcp_scraper` | парсинг каталога: `search_listings`, `get_listing`, `check_proxy_health` | — (импорт в gateway) | Фаза 2 |
| `avito_mcp_db` | `record_scan_result`, `get_price_history`, `export_listings`, `status` | `db` | Фаза 3 |
| `avito_mcp_notify` | уведомления (скелет: `status`) | `notify` | Фаза 1 |
| `avito_mcp_shared` | общие утилиты: `ServerRole`, `ROLE_NAMESPACES` | — | Фаза 1 |

Gateway больше не знает про Supabase: `scan_new_listings` собирает каталог через
scraper и делегирует персистент в db (`record_scan_result`); `get_price_history`
и `export_listings` — тоже из db. db монтируется и под неймспейсом `db_*`.

## Команды

Проверки и запуск каждого сервера — из его каталога:

```bash
cd servers/gateway && uv sync --dev && uv run python -m avito_mcp_server
cd servers/scraper && uv sync --dev && uv run python -m avito_mcp_scraper
cd servers/db      && uv sync --dev && uv run python -m avito_mcp_db
cd servers/notify  && uv sync --dev && uv run python -m avito_mcp_notify
```

Линт/типы/тесты в каждом сервере: `uv run ruff check .`, `uv run ruff
format --check .`, `uv run mypy src`, `uv run pytest -q`. Тесты хранилища в db
пропускаются без `AVITO_SUPABASE_DSN`. Общий замок — `servers/uv.lock`
(uv-workspace, каждый сервер — editable-член). Версии в 5 манифестах плагина
сверяет `python3 scripts/check_versions.py` (exit 0). CI —
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml).