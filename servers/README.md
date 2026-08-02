# avito-mcp-servers

Распределённый набор MCP-серверов плагина [`avito-mcp-plugin`](../README.md).
**Фаза 1 (скелет):** монолит `server/` переехал в gateway, добавлены заготовки
scraper/db/notify. Курс — композиция «gateway + ролевые серверы» по образцу
[dj-music](https://github.com/evgenygurin/dj-music-mcp/blob/main/docs/ARCHITECTURE.md):
`mount` + `create_proxy`, без переноса бизнес-логики (фазы 2–4).

```text
servers/
├── pyproject.toml            # uv-workspace: члены gateway/scraper/db/notify/shared
├── gateway/                  # «входная дверь»: движок + 7 тулз + mount+create_proxy
├── scraper/                  # скелет: парсер (логика — фаза 2)
├── db/                       # скелет: хранилище (логика — фаза 3)
├── notify/                   # скелет: уведомления (логика — фаза 4)
└── shared/                   # общие утилиты (роли, неймспейсы композиции)
```

## Роли

| Пакет | Роль | Неймспейс gateway | Стадия |
|---|---|---|---|
| `avito_mcp_server` (gateway) | движок + 7 тулз, `mount`+`create_proxy` | — | Фаза 1 |
| `avito_mcp_scraper` | парсинг каталога (скелет: `status`) | `scraper` | Фаза 1 |
| `avito_mcp_db` | хранилище (скелет: `status`) | `db` | Фаза 1 |
| `avito_mcp_notify` | уведомления (скелет: `status`) | `notify` | Фаза 1 |
| `avito_mcp_shared` | общие утилиты: `ServerRole`, `ROLE_NAMESPACES` | — | Фаза 1 |

## Команды

Проверки и запуск каждого сервера — из его каталога:

```bash
cd servers/gateway && uv sync --dev && uv run python -m avito_mcp_server
cd servers/scraper && uv sync --dev && uv run python -m avito_mcp_scraper
cd servers/db      && uv sync --dev && uv run python -m avito_mcp_db
cd servers/notify  && uv sync --dev && uv run python -m avito_mcp_notify
```

Линт/типы/тесты в каждом сервере: `uv run ruff check .`, `uv run ruff
format --check .`, `uv run mypy src`, `uv run pytest -q`. Общий замок —
`servers/uv.lock` (uv-workspace, каждый сервер — editable-член). Версии в
5 манифестах плагина сверяет `python3 scripts/check_versions.py` (exit 0).
CI — [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).