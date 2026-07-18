# Установка avito-mcp-plugin для OpenAI Codex

Плагин гибридный: **skills** (через нативный skill-discovery Codex) +
**MCP-сервер** (через `config.toml`). Настраиваются раздельно.

## Требования

- Git
- [`uv`](https://docs.astral.sh/uv/) (для MCP-сервера; команда `uvx`)

## 1. Skills

```bash
# Клонировать репозиторий
git clone https://github.com/evgenygurin/avito-mcp-plugin.git ~/.codex/avito-mcp-plugin

# Симлинк каталога skills в директорию, которую сканирует Codex
mkdir -p ~/.agents/skills
ln -s ~/.codex/avito-mcp-plugin/skills ~/.agents/skills/avito-mcp-plugin
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills"
cmd /c mklink /J "$env:USERPROFILE\.agents\skills\avito-mcp-plugin" "$env:USERPROFILE\.codex\avito-mcp-plugin\skills"
```

## 2. MCP-сервер

Добавьте в `~/.codex/config.toml` (или `.codex/config.toml` проекта):

```toml
[mcp_servers.avito]
command = "uvx"
args = [
    "--from",
    "git+https://github.com/evgenygurin/avito-mcp-plugin.git#subdirectory=server",
    "avito-mcp-server",
]

[mcp_servers.avito.env]
LOG_LEVEL = "info"
```

Готовый пример — [`../examples/mcp-configs/codex.toml`](../examples/mcp-configs/codex.toml).

> Codex не умеет streamable HTTP напрямую. Для remote-сервера нужен мост
> `mcp-proxy` (stdio ↔ HTTP). Для локального stdio-запуска мост не требуется.

## 3. Перезапуск

Перезапустите Codex (выйдите и запустите CLI заново), чтобы обнаружить skills и
поднять MCP-сервер.

## Проверка

- Skills должны появиться в списке доступных навыков Codex.
- MCP-сервер `avito` с тулзами парсинга Avito (`search_listings`, `get_listing`, … — 🔜 план) — в списке MCP.
- Сервер также раздаёт skills как ресурсы `skill://<name>/SKILL.md`.
