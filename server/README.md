# avito-mcp-server

MCP-сервер на [FastMCP v3](https://gofastmcp.com) для работы с Avito. Часть
плагина [`avito-mcp-plugin`](../README.md).

> **СТАТУС: ранняя разработка.** Движок парсинга воспроизведён и валидирован
> живьём (провайдер кук spfa → rotate-until-clean → curl_cffi + follow-редирект →
> `find_json_on_page`); раздача `skills/` по MCP (`SkillsProvider`) работает.
> **7 MCP-тулз** (`search_listings`, `get_listing`, `scan_new_listings`,
> `check_proxy_health`, `send_notification`, `export_listings`, `get_price_history`)
> — все в статусе **🔜 план** (см. [`../docs/mcp-server.md`](../docs/mcp-server.md)).

## Требования

- Python ≥ 3.12
- [`uv`](https://docs.astral.sh/uv/)

## Разработка

```bash
cd server
uv sync --dev            # установить зависимости (создаст .venv + uv.lock)
uv run avito-mcp-server  # запустить сервер (stdio)
uv run pytest -q         # тесты (in-memory Client(mcp))
uv run ruff check .      # линт
uv run mypy src          # типы
```

## Подключение к агенту

Плагин объявляет сервер через [`../.mcp.json`](../.mcp.json) (плоский формат).
На время разработки используется локальный запуск:

```json
{
  "avito": {
    "command": "uv",
    "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/server", "avito-mcp-server"]
  }
}
```

После публикации в PyPI вариант для распространения:

```json
{ "avito": { "command": "uvx", "args": ["avito-mcp-server"] } }
```

Конфигурация для других агентов (Cursor, Codex, Gemini CLI) — в
[`../docs/portability.md`](../docs/portability.md).

## Структура

```text
server/
├── pyproject.toml                     # uv_build, fastmcp>=3, httpx, project.scripts
├── src/avito_mcp_server/
│   ├── __init__.py
│   ├── server.py                      # FastMCP инстанс + main(), регистрация групп тулз
│   ├── models.py                      # доменные Pydantic-модели (Listing, SearchResult)
│   ├── parser.py                      # ядро: find_json_on_page + пагинация
│   ├── cookies/                       # провайдеры кук: spfa / own / playwright
│   ├── proxies/                       # Mobile/Server/None + rotate-until-clean
│   ├── http/                          # curl_cffi клиент (impersonate, retry)
│   ├── export/                        # xlsx / json / csv
│   ├── notifications/                 # Telegram, VK
│   ├── filters/                       # keyword/seller/price/geo/max_age
│   ├── storage/                       # sqlite: dedup + история цены
│   ├── skills_provider.py             # раздача skills/ по MCP (SkillsProvider)
│   └── tools/                         # тонкий MCP-слой (register(mcp) на группу)
└── tests/                             # pytest: in-memory Client(mcp) + мок сетевой границы
```
