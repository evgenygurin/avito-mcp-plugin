# Переносимость между агентами

Плагин переносим за счёт двух открытых слоёв: **MCP** (универсальный слой тулз,
один сервер — разные конфиги) и **Agent Skills** (`SKILL.md` по стандарту
agentskills.io). Ниже — как подключить сервер `avito` к разным агентам.

## Конфиги MCP по агентам

| Агент | Файл конфига | Формат | Ключ / нюанс |
|---|---|---|---|
| Claude Code | `.mcp.json` (проект), `~/.claude.json` (user) | JSON | `mcpServers`; `type: http/stdio`; `url` |
| Claude Desktop | `claude_desktop_config.json` | JSON | `mcpServers` |
| Cursor | `.cursor/mcp.json` | JSON | `mcpServers`; `type:"stdio"` |
| VS Code (Copilot) | `.vscode/mcp.json` | JSON | ключ **`servers`** (не `mcpServers`!), нужен `type` |
| OpenAI Codex CLI | `~/.codex/config.toml` | **TOML** | `[mcp_servers.<name>]`; `url` + `bearer_token_env_var` |
| Gemini CLI | `~/.gemini/settings.json` | JSON | `mcpServers`; для HTTP — **`httpUrl`** (не `url`) |
| Windsurf | `mcpServers` JSON | JSON | принимает алиас `serverUrl` |
| Cline | `mcpServers` JSON | JSON | + `disabled`, `alwaysAllow` |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` | JSON | `mcpServers` |
| opencode | `opencode.json` | JSON | `mcp` → `{type:"local", command:[...], enabled:true}` |

## Один сервер, два формата

```jsonc
// JSON (Claude Code / Cursor / Gemini / Cline / Windsurf)
{ "mcpServers": { "avito": { "command": "uvx", "args": ["avito-mcp-server"] } } }
```

```toml
# TOML (Codex CLI, ~/.codex/config.toml)
[mcp_servers.avito]
command = "uvx"
args = ["avito-mcp-server"]
[mcp_servers.avito.env]
LOG_LEVEL = "info"
```

## Три копипаст-ловушки

1. **Файл** — JSON vs TOML (Codex единственный на TOML).
2. **HTTP-поле** — `url` (Claude/Codex/Cursor) vs `httpUrl` (Gemini/Qwen).
3. **Top-level ключ** — `mcpServers` vs `servers` (VS Code).

SSE устарел — для remote используй streamable HTTP. Codex не умеет streamable
HTTP напрямую → нужен `mcp-proxy` как мост stdio↔HTTP.

## Перенос skills

`SKILL.md` по открытому стандарту подхватывают Claude Code, Codex, Cursor,
Gemini CLI, VS Code/Copilot, Goose, Kiro, Amp, Roo Code, Windsurf, Cline и др.
Директории: `~/.claude/skills`, `.agents/skills/` и аналоги.

Чтобы skills оставались переносимыми:

- держи в теле только открытые поля (`name`, `description`, Markdown);
- Claude-специфику выноси в опциональные поля/сайдкары;
- ссылайся на тулзы **словами-действиями**, не по имени рантайма.

Плюс общий `AGENTS.md` — файл инструкций проекта, который читают многие агенты.

## Тонкие адаптеры

По образцу superpowers переносимость усиливают тонкие адаптеры под каждый
harness: `.cursor-plugin/`, `.codex-plugin/`, `AGENTS.md`, `GEMINI.md`,
`gemini-extension.json`. В этом репозитории уже есть `AGENTS.md`, `GEMINI.md` и
`gemini-extension.json`; адаптеры Cursor/Codex — по мере необходимости.

## Раздача skills по MCP

FastMCP v3 `SkillsProvider` может выставлять `skills/` как MCP-ресурсы
(`skill://`, SEP-2640), чтобы те же файлы получал любой MCP-клиент. Фича молодая —
не все клиенты авто-подхватывают; рассматривать как дополнение. Подробнее —
[`mcp-server.md`](mcp-server.md).
