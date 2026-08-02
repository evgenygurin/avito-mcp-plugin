# avito-mcp-servers

Распределённый набор MCP-серверов плагина [`avito-mcp-plugin`](../README.md).
**Фаза 5:** движок парсинга — в scraper (stateless), хранилище/экспорт/история
цены — в db (единственный stateful-сервер, знает про Supabase), уведомления —
в notify. Gateway — входная дверь: тулзы scraper/db/notify проксируются в него
импортом, дополнительно db/notify монтируются как прокси под неймспейсами.

```text
servers/
├── pyproject.toml            # uv-workspace: члены gateway/scraper/db/notify/shared
├── gateway/ + avito_mcp_server  # «входная дверь»: чистая композиция (прокси импортом)
├── scraper/ + avito_mcp_scraper # движок парсинга (stateless): search/get_listing/check
├── db/     + avito_mcp_db       # единственный stateful-сервер: Supabase, история, экспорт
├── notify/ + avito_mcp_notify   # уведомления: send_notification (Telegram/VK)
└── shared/ + avito_mcp_shared   # общие утилиты (роли, неймспейсы композиции)
```

## Роли

| Пакет | Роль | Неймспейс gateway | Стадия |
|---|---|---|---|
| `avito_mcp_server` (gateway) | входная дверь (движок + scan + делегация db/notify + skills) | — | Фаза 5 |
| `avito_mcp_scraper` | парсинг каталога: `search_listings`, `get_listing`, `check_proxy_health` | — (импорт) | Фаза 2 |
| `avito_mcp_db` | `record_scan_result`, `get_price_history`, `export_listings`, `status` | `db` | Фаза 3 |
| `avito_mcp_notify` | `send_notification`, `status` | `notify` | Фаза 4 |
| `avito_mcp_shared` | общие утилиты: `ServerRole`, `ROLE_NAMESPACES` | — | Фаза 1 |

Gateway не знает ни про Supabase, ни про каналы уведомлений: `scan_new_listings`
собирает каталог через scraper и делегирует персистент в db (`record_scan_result`);
`get_price_history`/`export_listings` — из db; `send_notification` — из notify.
Скелеты db/notify дополнительно монтируются как прокси под неймспейсами
(`db_*`, `notify_*`).

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