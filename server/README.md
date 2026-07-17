# avito-mcp-server

MCP-сервер на [FastMCP v3](https://gofastmcp.com) для работы с Avito. Часть
плагина [`avito-mcp-plugin`](../README.md).

> **СТАТУС: ранняя разработка.** Реализованы: тулза `ping`, клиент официального
> API и тулза `official_api_call`, доменные модели, утилиты, раздача `skills/`
> по MCP (`SkillsProvider`) — 32 теста, ruff + mypy чисты. Парсинг-тулзы
> (`search_listings`, `get_listing`) — в разработке
> (см. [`../docs/mcp-server.md`](../docs/mcp-server.md)).

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
│   ├── server.py                      # FastMCP инстанс + main(), регистрация тулз
│   ├── models.py                      # доменные Pydantic-модели (Listing, SearchQuery, …)
│   ├── utils.py                       # детерминированные утилиты (extract_listing_id)
│   ├── official_api.py                # OAuth2-клиент официального API
│   ├── skills_provider.py             # раздача skills/ по MCP (SkillsProvider)
│   └── tools/
│       └── official_api.py            # тулза official_api_call (register(mcp))
└── tests/                             # pytest: in-memory Client(mcp) + httpx.MockTransport
```
