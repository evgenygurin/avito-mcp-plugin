# Конфиги MCP-сервера для разных агентов

Готовые конфигурации для подключения MCP-сервера `avito` к агентам, отличным от
Claude Code (у Claude Code — свой [`.mcp.json`](../../.mcp.json) в корне плагина).

Полная таблица форматов и нюансов — в [`docs/portability.md`](../../docs/portability.md).

| Агент | Файл конфига | Пример здесь | Нюанс |
|---|---|---|---|
| Cursor | `.cursor/mcp.json` | [`cursor.json`](cursor.json) | `mcpServers`, `type:"stdio"` |
| Gemini CLI | `.gemini/settings.json` | [`gemini.json`](gemini.json) | для HTTP — `httpUrl`, не `url` |
| VS Code (Copilot) | `.vscode/mcp.json` | [`vscode.json`](vscode.json) | ключ **`servers`**, не `mcpServers` |
| OpenAI Codex CLI | `~/.codex/config.toml` | [`codex.toml`](codex.toml) | **TOML**; нет streamable HTTP → `mcp-proxy` |

## Как использовать

1. Скопируйте нужный пример в конфиг-файл своего агента (см. столбец «Файл конфига»).
2. Уберите служебный ключ `"//"` (комментарий) из JSON-примеров.
3. Убедитесь, что установлен [`uv`](https://docs.astral.sh/uv/) (команда `uvx`).
4. Перезапустите агента — сервер `avito` появится в списке MCP.

## Транспорт

Примеры используют **stdio** и запуск через `uvx` из git (без клонирования).
После публикации пакета в PyPI аргумент `--from git+…` можно заменить на просто
`avito-mcp-server`:

```jsonc
{ "command": "uvx", "args": ["avito-mcp-server"] }
```

Для локальной разработки — вариант с `uv run --project <путь>/server` (см.
комментарий в [`codex.toml`](codex.toml) и [`../../.mcp.json`](../../.mcp.json)).

## Раздача skills по MCP

Сервер также раздаёт `skills/` как MCP-ресурсы (`skill://<name>/SKILL.md`) —
любой MCP-клиент может их получить (`list_resources` / `read_resource`). Это
работает поверх любого из конфигов выше.
