# Проектирование переносимого плагина для AI‑агентов: skills + встроенный MCP‑сервер (Python 3.12 / FastMCP v3 / uv)

## TL;DR
- **Оптимальная архитектура — «толстое ядро + тонкие адаптеры»: один Python‑пакет с MCP‑сервером на FastMCP v3 (детерминированные тулзы), опубликованный в PyPI и запускаемый через `uvx`, плюс набор переносимых `SKILL.md` (процедурные инструкции по открытому стандарту Agent Skills). Claude Code получает всё это как plugin через `.claude-plugin/plugin.json` + `.mcp.json`; другие агенты (Cursor, Codex, Gemini CLI, Cline и т.д.) подключают тот же MCP‑сервер через свои `mcp.json`/`config.toml`, а skills — через директории `~/.claude/skills` / `.agents/skills` и т.п.**
- **Superpowers (obra/superpowers, Jesse Vincent, v6.1.1) — это НЕ MCP‑плагин: его ядро это ровно 14 композируемых skills + hooks + commands, без встроенного MCP‑сервера.** MCP‑серверы у него живут в отдельных плагинах маркетплейса (private-journal-mcp, superpowers-chrome). Ваша задача — гибрид, которого у superpowers в ядре нет: skills + собственный Python MCP‑сервер в одном репозитории.
- **FastMCP v3.0 GA вышел 18 февраля 2026; API поверхности (`@mcp.tool` и т.п.) почти не изменился, но под капотом — новая архитектура Provider/Transform (включая `SkillsProvider` — раздача skills через MCP).** Практический стек 2026: `uv` + `uv_build`/`hatchling`, src‑layout, `fastmcp>=3`, публикация в PyPI, in‑memory тестирование через `Client(mcp)`, CI на GitHub Actions (ruff/mypy/pytest/publish).

---

## Key Findings

1. **Superpowers — методология, а не тулзы.** Это «agentic skills framework & software development methodology». Ядро = 14 skills, которые триггерятся автоматически по описанию, плюс session‑start hook, который инжектит bootstrap‑инструкцию. Ключевые skills: `brainstorming`, `writing-plans`, `test-driven-development`, `subagent-driven-development`, `systematic-debugging`, `writing-skills`, `using-superpowers`. MCP в ядре отсутствует. Репозиторий крайне популярен — 256 000 звёзд и 22 800 форков на GitHub (страница Releases, июль 2026).
2. **Формат плагина Claude Code стабилизирован.** Единственный обязательный файл — `.claude-plugin/plugin.json`; все компоненты (`skills/`, `commands/`, `agents/`, `hooks/`, `.mcp.json`) лежат в корне плагина, НЕ внутри `.claude-plugin/`. MCP‑сервер объявляется через `.mcp.json` (плоский формат) либо inline `mcpServers` в plugin.json, с переменной `${CLAUDE_PLUGIN_ROOT}`.
3. **Agent Skills — открытый стандарт (agentskills.io), принят десятками инструментов.** `SKILL.md` = YAML‑frontmatter (`name`, `description` обязательны) + Markdown‑тело; трёхуровневый progressive disclosure. Это делает skills переносимыми между Claude Code, Codex, Cursor, Gemini CLI, VS Code и др.
4. **MCP — универсальный слой совместимости.** Один MCP‑сервер подключается ко всем агентам; различаются только конфиги (JSON vs TOML, `url` vs `httpUrl`, пути файлов).
5. **FastMCP v3 = production‑grade.** Новое: providers (FileSystem, OpenAPI, Proxy, **Skills**), transforms, component versioning, per‑component auth, OpenTelemetry, session state, hot reload, callable‑декораторы. По README PrefectHQ/fastmcp автор Jeremiah Lowin отмечает: «downloaded a million times a day, and some version of FastMCP powers 70% of MCP servers across all languages» (отдельные обзоры дают уже ~1.9 млн загрузок/день). Breaking changes минимальны, но реальны (см. таблицу миграции).
6. **uv/uvx — стандарт дистрибуции Python MCP‑серверов в 2026.** `uvx --from git+... server` или `uvx <pypi-package>` — одна команда, изолированное окружение, автоскачивание Python. Реальные плагины уже используют этот паттерн.

---

## Details

### 1. Репозиторий Superpowers (obra/superpowers)

**Автор:** Jesse Vincent (jesse@fsck.com), Prime Radiant. **Лицензия:** MIT. **Версия:** v6.1.1 — по странице Releases: «obra released this · 02 Jul 21:58 · v6.1.1 Latest · Codex no longer re-registers the Claude SessionStart hook». По составу это **skills‑framework, а не MCP‑плагин** (256k звёзд / 22.8k форков).

**Реальный `.claude-plugin/plugin.json` (ядро):**
```json
{
  "name": "superpowers",
  "description": "Core skills library for Claude Code: TDD, debugging, collaboration patterns, and proven techniques",
  "version": "6.1.1",
  "author": { "name": "Jesse Vincent", "email": "jesse@fsck.com" },
  "homepage": "https://github.com/obra/superpowers",
  "repository": "https://github.com/obra/superpowers",
  "license": "MIT",
  "keywords": ["skills", "tdd", "debugging", "collaboration", "best-practices", "workflows"]
}
```
Обратите внимание: **нет поля `mcpServers`** и нет `.mcp.json`. Ядро — чистые skills + hooks + commands + agents.

**Структура репозитория (main):**
```
superpowers/
├── .claude-plugin/       # plugin.json (+ marketplace.json в отд. репо)
├── .codex-plugin/        # адаптер под OpenAI Codex
├── .cursor-plugin/       # адаптер под Cursor (plugin.json: skills/agents/commands/hooks)
├── .kimi-plugin/  .opencode/  .pi/extensions/  .agents/plugins/
├── .github/
├── hooks/                # session-start bootstrap и пр.
├── skills/               # 14 скиллов (см. ниже)
├── commands/  agents/  scripts/  tests/  docs/  assets/
├── AGENTS.md  CLAUDE.md  GEMINI.md  gemini-extension.json  package.json
└── README.md
```
Наличие `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `.opencode/`, `.pi/`, `AGENTS.md`, `GEMINI.md` показывает главный приём переносимости: **один репозиторий skills + тонкие адаптеры под каждый harness.** Skills «говорят действиями», а не именами тулзов конкретного рантайма, и per‑harness маппинг тулзов лежит в `skills/using-superpowers/references/`.

**Список skills (по категориям, из README):**
- *Testing:* `test-driven-development` (RED‑GREEN‑REFACTOR + антипаттерны).
- *Debugging:* `systematic-debugging` (4‑фазный root‑cause), `verification-before-completion`.
- *Collaboration:* `brainstorming` (сократический дизайн), `writing-plans`, `executing-plans`, `dispatching-parallel-agents`, `requesting-code-review`, `receiving-code-review`, `using-git-worktrees`, `finishing-a-development-branch`, `subagent-driven-development`.
- *Meta:* `writing-skills` (как писать скиллы), `using-superpowers` (bootstrap).

Всего **ровно 14 композируемых скиллов** по стандарту agentskills.io в ядре (маркетинговые листинги пишут «20+», считая связанные плагины маркетплейса).

**Установка (Claude Code):**
```
/plugin install superpowers@claude-plugins-official          # официальный маркетплейс Anthropic
# или
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

**Родственные репозитории:**
- `obra/superpowers-marketplace` — каталог (`.claude-plugin/marketplace.json`), включает `superpowers`, `elements-of-style`, `episodic-memory`, `superpowers-lab`, `superpowers-chrome`, `private-journal-mcp`, `superpowers-developing-for-claude-code`.
- `obra/superpowers-skills` — community‑editable skills.
- `obra/superpowers-lab` — экспериментальные skills.
- `obra/private-journal-mcp` — отдельный MCP‑сервер (Node/npx, semantic search). **Именно так superpowers поставляет MCP — отдельным плагином, а не в ядре.**
- `obra/superpowers-developing-for-claude-code` — skills для разработки плагинов (42+ файла офиц. документации).
- Сторонний `erophames/superpowers-mcp` — оборачивает skills superpowers в MCP‑сервер для любых MCP‑клиентов.

**Философия:** TDD (тесты первыми), systematic over ad‑hoc, complexity reduction, evidence over claims. `writing-skills` формализует «documentation TDD»: skill — это переиспользуемый reference (техника/паттерн/инструмент), а не нарратив «как я однажды решил проблему»; skill тестируется на других агентах до публикации.

### 2. Формат плагинов Claude Code (спецификация 2026)

**Каноническое правило:** только `plugin.json` лежит в `.claude-plugin/`. Всё остальное — в корне плагина. Если положить `skills/` внутрь `.claude-plugin/`, плагин загрузится, но компоненты будут невидимы (тихий провал).

**Полная схема `.claude-plugin/plugin.json`:**
```json
{
  "name": "plugin-name",
  "version": "1.2.0",
  "description": "Brief plugin description",
  "author": { "name": "Author Name", "email": "author@example.com", "url": "https://github.com/author" },
  "homepage": "https://docs.example.com/plugin",
  "repository": "https://github.com/author/plugin",
  "license": "MIT",
  "keywords": ["keyword1", "keyword2"],
  "commands": ["./custom/commands/special.md"],
  "agents": "./custom/agents/",
  "skills": "./custom/skills/",
  "hooks": "./config/hooks.json",
  "mcpServers": "./mcp-config.json",
  "outputStyles": "./styles/",
  "lspServers": "./.lsp.json"
}
```
- Обязательно только `name`. Компонентные поля (`commands`/`agents`/`skills`/`hooks`/`mcpServers`/`outputStyles`/`lspServers`) — опциональны; если указать кастомный путь для `skills`, дефолтная `skills/` больше не сканируется (добавляйте дефолт явно: `"skills": ["./skills/", "./extras/"]`).
- Пути должны начинаться с `./` и быть внутри плагина. Пути наружу (`../shared`) не работают: при установке плагин копируется в кэш (`~/.claude/plugins/cache`). Symlinks внутри плагина сохраняются; symlinks в пределах маркетплейса дереференсятся; наружу — пропускаются (security).

**MCP‑сервер в плагине.** Два способа:
1. Отдельный `.mcp.json` в корне плагина (**плоский формат — без обёртки `mcpServers`** внутри самого `.mcp.json`, по факту всех официальных плагинов):
```json
{
  "my-py-tools": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/you/plugin.git#subdirectory=server", "my-mcp-server"],
    "env": { "LOG_LEVEL": "info" }
  }
}
```
2. Inline в plugin.json (поле `mcpServers` — обёртка нужна):
```json
{ "name": "my-plugin", "mcpServers": { "my-py-tools": { "command": "${CLAUDE_PLUGIN_ROOT}/servers/run.sh" } } }
```
> Важно: в официальной документации есть путаница — пример `.mcp.json` ошибочно показывает обёртку `mcpServers`. По факту всех официальных плагинов Anthropic `.mcp.json` использует **плоский** формат (ключ = имя сервера сразу на верхнем уровне). Поле `mcpServers` — это концепт plugin.json, которое может либо ссылаться на внешний файл, либо описывать серверы inline.

**Переменные окружения:**
- `${CLAUDE_PLUGIN_ROOT}` — абсолютный путь к установленному плагину (в кэше). Обязательна для всех внутриплагинных путей.
- `${CLAUDE_PROJECT_DIR}` — корень проекта.
- `${CLAUDE_PLUGIN_DATA}` — персистентная data‑директория плагина (удаляется при деинсталляции).
- `${VAR}` / `${VAR:-default}` — раскрытие env в `.mcp.json`.

Плагинные MCP‑серверы стартуют автоматически при включении плагина (не через `/mcp`). После правок — `/reload-plugins`.

**Формат `SKILL.md` (Claude Code).** Frontmatter (проверено по code.claude.com):
```markdown
---
name: my-skill                      # опц., по умолчанию = имя директории; lowercase+hyphens, ≤64
description: >                      # ОБЯЗАТЕЛЬНО (что делает + КОГДА применять), ≤1024/1536 симв.
  Use when [условие] — [что делает]. Include trigger keywords.
allowed-tools: Read, Grep, Bash(git:*)   # опц. (с дефисом!), пред-одобренные тулзы
argument-hint: "[issue-number]"    # опц., подсказка в автокомплите
disable-model-invocation: false    # опц., true = только пользователь может вызвать
user-invocable: true               # опц., false = скрыть из / меню (только Claude)
model: inherit                     # опц., переопределить модель для скилла
context: fork                      # опц., запуск в изолированном subagent
agent: Explore                     # опц., тип subagent при context: fork
---
# My Skill
[инструкции; держать тело < 500 строк / ~5k токенов; детали — в references/]
```
Дополнительные официальные поля Claude Code (по code.claude.com): `when_to_use`, `arguments`, `disallowed-tools`, `effort` (low/medium/high/xhigh/max), `hooks`, `paths`, `shell` (bash/powershell). **Только `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` — часть открытого стандарта; остальное — расширения Claude Code.** Написание `allowed-tools` — с дефисом (подтверждено официальной документацией).

**Progressive disclosure (3 уровня):**
1. Startup: агент грузит только `name`+`description` каждого скилла (~80–100 токенов/скилл) в системный промпт.
2. Activation: при совпадении задачи грузится полное тело `SKILL.md` (рекоменд. < 5k токенов).
3. Execution: `scripts/` (выполняются, код не входит в контекст), `references/` (грузятся по требованию), `assets/` (шаблоны/статика).

**Структура каталогов плагина:**
```
my-plugin/
├── .claude-plugin/plugin.json     # ТОЛЬКО манифест
├── skills/<name>/SKILL.md         # + scripts/ references/ assets/
├── commands/*.md                  # слэш-команды
├── agents/*.md                    # субагенты (нельзя: hooks, mcpServers, permissionMode)
├── hooks/hooks.json               # события: PreToolUse, PostToolUse, SessionStart, ...
└── .mcp.json                      # MCP-серверы (плоский формат)
```

**Маркетплейс (`.claude-plugin/marketplace.json`, в корне репо):**
```json
{
  "name": "your-marketplace",
  "owner": { "name": "You", "email": "you@example.com" },
  "plugins": [
    { "name": "your-plugin", "source": "./plugins/your-plugin", "version": "0.1.0",
      "description": "...", "category": "development", "keywords": ["..."] }
  ]
}
```
- `source` может быть относительным путём, либо объектом (`{"source":"github","repo":"o/r","ref":"v1","sha":"..."}`), либо `{"source":"url","url":"...git"}`.
- `strict:false` — запись маркетплейса служит полным манифестом, если plugin.json отсутствует.
- Зарезервированные имена: `claude-code-marketplace`, `claude-plugins-official`, `agent-skills` и др.
- Относительные пути работают только при добавлении маркетплейса через git (не через прямой URL на marketplace.json).

**Установка/публикация/отладка:**
```
/plugin marketplace add owner/repo        # (или git URL, локальный путь, remote URL)
/plugin install plugin@marketplace
claude --plugin-dir ./my-plugin           # загрузить локально на сессию (без установки)
/reload-plugins                           # перечитать после правок
claude plugin validate ./my-plugin        # проверка манифеста и frontmatter
claude --debug                            # смотреть "loading plugin" сообщения
# сброс кэша: rm -rf ~/.claude/plugins/cache
claude plugin list [--enabled|--disabled]
```

### 3. Совместимость с другими агентами

**Два переносимых слоя:**
- **MCP** — универсальный слой тулзов. Один сервер, разные конфиги.
- **Agent Skills (SKILL.md)** — открытый стандарт (agentskills.io), принят множеством инструментов (Claude Code, OpenAI Codex, Cursor, Gemini CLI, VS Code/Copilot, Goose, Kiro, Junie, Amp, Roo Code, Windsurf, Cline и др.). Портативность skills — явная цель стандарта. Плюс `AGENTS.md` — общий файл инструкций проекта.

**Таблица конфигов MCP по агентам:**

| Агент | Файл конфига | Формат | Ключ / нюанс |
|---|---|---|---|
| Claude Code | `.mcp.json` (проект), `~/.claude.json` (user) | JSON | `mcpServers`; `type: http/stdio`; `url` |
| Claude Desktop | `claude_desktop_config.json` | JSON | `mcpServers` |
| Cursor | `.cursor/mcp.json` (проект), `~/.cursor/mcp.json` (user) | JSON | `mcpServers`; `type:"stdio"` |
| VS Code (Copilot) | `.vscode/mcp.json` / `.github/mcp.json` | JSON | ключ **`servers`** (не `mcpServers`!), нужен `type` |
| OpenAI Codex CLI | `~/.codex/config.toml` / `.codex/config.toml` | **TOML** | `[mcp_servers.<name>]`; `url` + `bearer_token_env_var` |
| Gemini CLI | `~/.gemini/settings.json` / `.gemini/settings.json` | JSON | `mcpServers`; для HTTP — **`httpUrl`** (не `url`) |
| Windsurf | `mcpServers` JSON | JSON | принимает алиас `serverUrl` |
| Cline | `mcpServers` JSON | JSON | + `disabled`, `alwaysAllow` |
| GitHub Copilot CLI | `~/.copilot/mcp-config.json` | JSON | `mcpServers` |
| opencode | `opencode.json` | JSON | `mcp` → `{type:"local", command:[...], enabled:true}` |

**Пример одного и того же сервера в двух форматах:**
```jsonc
// JSON (Claude Code / Cursor / Gemini / Cline / Windsurf)
{ "mcpServers": { "my-tools": { "command": "uvx", "args": ["my-mcp-server"] } } }
```
```toml
# TOML (Codex CLI, ~/.codex/config.toml)
[mcp_servers.my-tools]
command = "uvx"
args = ["my-mcp-server"]
[mcp_servers.my-tools.env]
LOG_LEVEL = "info"
```

**Три копипаст‑ловушки при переносе конфига:** (1) файл — JSON vs TOML (Codex единственный TOML); (2) HTTP‑поле — `url` (Claude/Codex/Cursor) vs `httpUrl` (Gemini/Qwen); (3) top‑level ключ — `mcpServers` vs `servers` (VS Code). SSE устарел — для remote используйте streamable HTTP. Codex не умеет streamable HTTP напрямую — нужен `mcp-proxy` как мост stdio↔HTTP.

**Раздача skills другим агентам через MCP.** FastMCP v3 `SkillsProvider` (см. ниже) выставляет директории skills как MCP‑ресурсы (`skill://` URI). Это официальный путь SEP‑2640 (Skills Extension, `io.modelcontextprotocol/skills`). То есть можно сервить один и тот же `SKILL.md` любому MCP‑клиенту.

**Рецепт максимальной переносимости:**
1. Вся детерминированная логика — в MCP‑сервере (FastMCP), публикуем в PyPI.
2. Процедурные инструкции — в `SKILL.md` по открытому стандарту (чистое ядро: `name`, `description`, Markdown; Claude‑специфику — в опциональные поля/сайдкары).
3. Тонкие адаптеры под каждый harness (как в superpowers: `.cursor-plugin/`, `.codex-plugin/`, `AGENTS.md`, `GEMINI.md`).
4. Опционально — `SkillsProvider` в самом MCP‑сервере, чтобы skills тоже раздавались по MCP.

### 4. FastMCP v3+ (актуально на 2026)

**Timeline (из issue #3125):** Beta 1 — 20 янв 2026; Beta 2 — 6 фев; RC1 — 12 фев; **GA 3.0.0 «Three at Last» — 18 фев 2026** (Jeremiah Lowin: «FastMCP 3.0 is stable and generally available»). На момент исследования актуальна ветка 3.4.x — `fastmcp 3.4.4` (PyPI, загружен через uv/0.11.28), release note: «FastMCP 3.4.4 restores HTTP deployment compatibility after the 3.4.3 Host/Origin guard changed default behavior… adds Hugging Face OAuth provider support». Репозиторий переехал `jlowin/fastmcp` → `PrefectHQ/fastmcp` (редиректы работают, PyPI/импорты те же). Лицензия Apache‑2.0, автор Jeremiah Lowin.

**Что нового в v3 vs v2 (концептуально):**
- **Provider/Transform архитектура.** Provider = «откуда берутся компоненты» (декораторы `LocalProvider`, `FileSystemProvider`, `OpenAPIProvider`, `ProxyProvider`, `SkillsProvider`, кастомные). Transform = middleware над потоком компонентов (rename, namespace, filter, version, visibility). `mount()` теперь = Provider + Namespace‑transform; проксирование = Provider поверх MCP‑клиента.
- **`SkillsProvider` / `ClaudeSkillsProvider` / `CursorSkillsProvider` / `CodexSkillsProvider`** — раздача skills как MCP‑ресурсов; клиент FastMCP умеет `list_skills()`, `download_skill()`, `sync_skills()`.
- **Component versioning:** `@tool(version="2.0")` рядом со старой версией; `VersionFilter`.
- **Per‑component auth** (`auth=`, `require_scopes`), `AuthMiddleware`; OAuth 2.1, DCR, OAuthProxy, CIMD, Static Client Registration, Azure OBO.
- **OpenTelemetry** нативно; session state (async, persistent); background tasks (Redis, опц. `fastmcp[tasks]`).
- **DX:** hot reload (`fastmcp dev server.py`, флаг `--reload`), декораторы возвращают исходную функцию (callable для тестов), sync‑тулзы автоматически уходят в threadpool.

**Breaking changes v2→v3 (главные):**

| Область | Было (v2) | Стало (v3) |
|---|---|---|
| Transport в конструкторе | `FastMCP("s", host=..., port=...)` | только `mcp.run(transport="http", host=..., port=...)` |
| Убранные kwargs | `host,port,log_level,debug,sse_path,json_response,stateless_http,on_duplicate_*,tool_serializer,include_tags,exclude_tags` | в `run()`/env/`on_duplicate=`/`ToolResult`/`enable/disable`/transforms |
| Enable/disable | `tool.disable()` | `server.disable(names={"t"}, components={"tool"})` |
| Листинг | `get_tools()` → dict | `list_tools()` → list |
| Prompts | `PromptMessage(role=..., content=TextContent(...))` | `Message("Hello")` (из `fastmcp.prompts`) |
| State | `ctx.set_state()/get_state()` sync | `await ctx.set_state()/get_state()` (JSON‑serializable) |
| Auth env | авто из `FASTMCP_SERVER_AUTH_*` | явно `client_id=os.environ[...]` |
| WSTransport | есть | удалён → `StreamableHttpTransport` |
| Декораторы | возвращают `FunctionTool` | возвращают функцию (для v2‑совместимости `FASTMCP_DECORATOR_MODE=object`) |
| Meta namespace | `_fastmcp` | `fastmcp` |
| Deprecated | `mount(prefix=)`, `import_server()`, `as_proxy()`, `add_tool_transformation()` | `mount(namespace=)`, `mount()`, `create_proxy()`, `add_transform()` |

Пин: `fastmcp>=3.0.0,<4`. `pip install fastmcp` НЕ обновит существующую установку — нужен `--upgrade` / `uv add --upgrade fastmcp`.

**API‑обзор (v3):**
```python
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

mcp = FastMCP("my-tools")

class QueryResult(BaseModel):
    rows: list[dict]
    count: int

@mcp.tool                                  # tool: side effects (POST/PUT)
async def query_db(sql: str, limit: int = 100, ctx: Context = None) -> QueryResult:
    """Execute a read-only SQL query against analytics DB and return rows as JSON."""
    await ctx.info(f"running: {sql[:50]}")  # логирование в клиент
    await ctx.report_progress(0, 1)         # прогресс
    rows = await run(sql, limit)            # ваша async-логика
    return QueryResult(rows=rows, count=len(rows))  # → structured content автоматически

@mcp.resource("schema://tables")           # resource: read-only (GET)
def list_tables() -> list[str]: ...

@mcp.resource("users://{user_id}/profile") # resource template
def profile(user_id: str) -> dict: ...

@mcp.prompt                                # prompt: reusable template
def review(code: str) -> str: return f"Review:\n{code}"
```
- **Context DI:** параметр с типом `Context` исключается из схемы; даёт `ctx.info/debug/warning/error`, `ctx.report_progress`, `ctx.sample()` (LLM sampling, в v3 concurrent с `tool_concurrency=0`), `ctx.elicit()` (структурный запрос у пользователя), `ctx.read_resource()`, `await ctx.set_state/get_state`, `ctx.session_id`.
- **Structured output:** возврат Pydantic/dataclass/dict → автоматически `structuredContent` + текстовый блок (backward compat). Схема генерится из аннотации возврата.
- **Elicitation:**
```python
from fastmcp import Context
class Confirm(BaseModel):
    confirm: bool = Field(description="Confirm?")
@mcp.tool
async def act(ctx: Context) -> str:
    r = await ctx.elicit("Proceed?", schema=Confirm)
    ...
```
- **Auth (resource server через JWT):**
```python
from fastmcp.server.auth.providers.jwt import JWTVerifier
auth = JWTVerifier(jwks_uri="https://idp/.well-known/jwks.json",
                   issuer="https://idp", audience="my-mcp")
mcp = FastMCP("Protected", auth=auth)
```
`JWTVerifier` (JWKS/public key/HS256), `StaticTokenVerifier` (dev), `IntrospectionTokenVerifier` (RFC 7662), `OAuthProxy`, `GitHubProvider`/`ClerkProvider`/`AuthKitProvider`. `BearerAuthProvider` deprecated.
- **Transports:** stdio (дефолт), streamable HTTP (рекоменд. для remote), SSE (deprecated). Запуск: `mcp.run()` / `mcp.run(transport="http", host="0.0.0.0", port=8080)`. ASGI: `app = mcp.http_app(path="/", transport="streamable-http")` — монтируется в FastAPI (`app.mount("/mcp", mcp_app)`), тогда CORS/auth/логирование внешнего FastAPI переиспользуются.
- **Composition:** `mcp.mount(sub, namespace="ns")`; проксирование `create_proxy("http://remote/mcp")`.
- **Providers:** `mcp.add_provider(SkillsDirectoryProvider(roots=Path.home()/".claude"/"skills"))`; `FileSystemProvider(reload=True)` для hot‑reload тулзов из файлов; `OpenAPIProvider(spec, httpx_client)`.

**Тестирование (in‑memory):**
```python
import pytest
from fastmcp import FastMCP, Client
from server import mcp

@pytest.fixture
def server(): return mcp

async def test_query(server):
    async with Client(server) as client:          # in-memory, без сети/сабпроцесса
        res = await client.call_tool("query_db", {"sql": "SELECT 1"})
        assert res.data["count"] == 1             # .content[0].text для сырого
```
Плюс `run_server_async(mcp)` (`fastmcp.utilities.tests`) для HTTP‑интеграционных тестов; `inline-snapshot` для схем; MCP Inspector (`npx @modelcontextprotocol/inspector`) для ручной отладки. Примечание для senior‑разработчика: как раз ваш стек (async SQLAlchemy/PG/Redis) отлично ложится — тулзы `async def`, `lifespan` для пула соединений, in‑memory `Client(mcp)` + SQLite `:memory:` для юнит‑тестов, интеграционные тесты помечайте `@pytest.mark.integration`.

**Деплой:** `fastmcp run server.py` / `fastmcp run fastmcp.json`; декларативный `fastmcp.json` (source/environment/deployment — «где/что/как»); Docker; **FastMCP Cloud** (`*.fastmcp.app/mcp`, деплой из GitHub). Host/Origin валидация включена по умолчанию (защита от DNS rebinding).

### 5. uv + Python 3.12 для MCP‑сервера

**src‑layout проект (рекомендуемый):**
```
my-mcp-server/
├── pyproject.toml
├── uv.lock
├── README.md
├── .python-version            # 3.12
├── src/my_mcp_server/
│   ├── __init__.py
│   ├── server.py              # FastMCP инстанс + main()
│   └── tools/…
└── tests/test_server.py
```

**`pyproject.toml` (uv_build — дефолт с июля 2025, production‑stable):**
```toml
[project]
name = "my-mcp-server"
version = "0.1.0"
description = "MCP server (FastMCP v3)"
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
dependencies = ["fastmcp>=3.0.0,<4"]

[project.scripts]
my-mcp-server = "my_mcp_server.server:main"     # entry point → uvx-команда

[build-system]
requires = ["uv_build>=0.11,<0.12"]
build-backend = "uv_build"

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio", "ruff", "mypy"]
```
> **uv_build vs hatchling:** для чистого Python — `uv_build` (в 10–35× быстрее, zero‑config, автодискавери src/flat layout, можно билдить без установленного Python). `hatchling` — если нужны build‑hooks, VCS‑версионирование (`hatch-vcs`), гибкий выбор файлов. Оба совместимы с `uv build`/`uv publish`.

**`server.py`:**
```python
from fastmcp import FastMCP
mcp = FastMCP("my-mcp-server")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def main() -> None:
    mcp.run()          # stdio по умолчанию

if __name__ == "__main__":
    main()
```

**Рабочий цикл uv:**
```bash
uv init --package --lib my-mcp-server   # или uv init --package
uv add "fastmcp>=3"
uv add --dev pytest pytest-asyncio ruff mypy
uv run my-mcp-server                     # локальный запуск
uv run pytest
uv lock                                  # uv.lock — фиксирует ВСЮ дерево зависимостей + хэши (коммитить!)
uv build                                 # sdist + wheel
uv publish                               # в PyPI (или --publish-url TestPyPI)
```

**Запуск клиентом через uvx (три режима дистрибуции):**
```jsonc
// 1) Локальная разработка (правки подхватываются сразу)
{ "command": "uv", "args": ["run", "my-mcp-server"] }

// 2) Из GitHub без клона (uvx = uv tool run)
{ "command": "uvx",
  "args": ["--from", "git+https://github.com/you/my-mcp-server.git", "my-mcp-server"] }

// 3) Из PyPI (после publish)
{ "command": "uvx", "args": ["my-mcp-server"] }
```
uvx читает `pyproject.toml`: проверяет `requires-python` (при нужде скачивает Python 3.12), ставит `dependencies` в кэш, регистрирует `project.scripts` как команду, запускает в изолированном временном окружении (кэш → второй запуск мгновенный). Для приватного git без PyPI: `--from "pkg @ git+https://…#subdirectory=path"` (+ `[tool.hatch.metadata] allow-direct-references = true` если hatchling). Реальный пример плагина с uvx: **ToolUniverse (mims-harvard/ToolUniverse)** — Claude Code plugin, чей `.mcp.json` запускает PyPI‑пакет `tooluniverse` через `uvx` (`{"command":"uvx","args":["tooluniverse"],"env":{...}}`).

**PEP 723 (single‑file MCP).** Для утилит/прототипов — inline‑метаданные без pyproject.toml:
```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["fastmcp>=3"]
# ///
from fastmcp import FastMCP
mcp = FastMCP("mini")
@mcp.tool
def ping() -> str: return "pong"
if __name__ == "__main__": mcp.run()
```
Запуск: `uv run server.py`; лок: `uv lock --script server.py`; в клиенте: `{"command":"uv","args":["run","server.py"]}`. Для плагина Claude Code это НЕ рекомендуется как основной путь (лучше пакет+uvx), но годится для минимальных серверов.

### 6. Архитектура плагина: skills + MCP в одном репо

**Когда что использовать:**

| Механизм | Для чего | Контекст |
|---|---|---|
| **MCP tool** | Детерминированные операции, side‑effects, точные вычисления, доступ к БД/API. Код НЕ входит в контекст. | Python/FastMCP |
| **Skill (SKILL.md)** | Процедурное знание, «как думать», workflow, паттерны, чек‑листы. Инжектится в контекст при триггере. | Markdown |
| **Command** | Явный слэш‑триггер пользователя (`/deploy`). | Markdown |
| **Subagent (agent)** | Изолированный контекст под задачу (review, explore); нельзя объявлять hooks/mcpServers/permissionMode. | Markdown |
| **Hook** | Реакция на события (SessionStart bootstrap, PostToolUse форматирование). | JSON+script |

Правило superpowers: если что‑то enforce‑ится регуляркой/валидацией — автоматизируйте (tool/hook), а документацию оставляйте для суждений (skill). Скилл ссылается на тулзу словами‑действиями, не завязываясь на имя тулза конкретного рантайма → переносимость.

**Как MCP‑сервер поставляется вместе с плагином (2 стратегии):**
- **A. uvx из PyPI (рекомендуется для публичного распространения):** `.mcp.json` → `uvx my-mcp-server`. Плюсы: версионирование через PyPI, нет вендоринга Python‑кода в плагин, чистое обновление. Минус: требует установленного `uv` у пользователя.
- **B. Локальный путь через `${CLAUDE_PLUGIN_ROOT}`:** сервер лежит внутри плагина, запуск `uv run --project ${CLAUDE_PLUGIN_ROOT}/server ...` или скрипт. Плюс: self‑contained. Минус: плагин копируется в кэш, окружение надо готовить (`${CLAUDE_PLUGIN_DATA}` для persistent данных).

**Версионирование:** SemVer в двух местах — `plugin.json.version` (кэш‑ключ Claude Code для апдейта) и `pyproject.toml.version` (PyPI). Держите синхронно (CI‑bump). FastMCP не версионирует тулзы автоматически — при breaking‑изменении сигнатуры тулза либо бампайте major, либо используйте `@tool(version=...)`.

**Progressive disclosure на уровне репо:** тонкие `SKILL.md` (< 500 строк) + `references/` + `scripts/`; тяжёлая логика — в MCP‑тулзах (код не ест контекст).

### 7. Практический скелет репозитория

```
my-superplugin/                          # git-репо = и плагин, и MCP-пакет
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json                            # MCP-сервер (плоский формат, uvx)
├── skills/
│   ├── using-my-tools/SKILL.md
│   └── doing-x/SKILL.md
├── commands/run-x.md
├── agents/reviewer.md
├── hooks/hooks.json
├── server/                              # Python-пакет MCP-сервера (src-layout)
│   ├── pyproject.toml
│   ├── uv.lock
│   └── src/my_mcp_server/{__init__.py,server.py,tools/…}
├── tests/test_server.py
├── .github/workflows/ci.yml
├── AGENTS.md                            # переносимость (общий стандарт)
├── README.md
└── LICENSE
```

**`.claude-plugin/plugin.json`:**
```json
{
  "name": "my-superplugin",
  "version": "0.1.0",
  "description": "Skills + Python MCP tools for X",
  "author": { "name": "You", "email": "you@example.com" },
  "homepage": "https://github.com/you/my-superplugin",
  "repository": "https://github.com/you/my-superplugin",
  "license": "MIT",
  "keywords": ["skills", "mcp", "python"]
}
```

**`.mcp.json` (плоский формат, uvx из PyPI):**
```json
{
  "my-tools": {
    "command": "uvx",
    "args": ["my-mcp-server"],
    "env": { "LOG_LEVEL": "info" }
  }
}
```
Локальный вариант на время разработки:
```json
{
  "my-tools": {
    "command": "uv",
    "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/server", "my-mcp-server"]
  }
}
```

**`.claude-plugin/marketplace.json`** (в отдельном репо‑каталоге или в этом же):
```json
{
  "name": "my-marketplace",
  "owner": { "name": "You" },
  "plugins": [
    { "name": "my-superplugin", "source": "./", "description": "Skills + MCP tools", "category": "development" }
  ]
}
```

**`server/pyproject.toml`** — см. раздел 5 (uv_build, `project.scripts`, `fastmcp>=3`).

**`server/src/my_mcp_server/server.py`:**
```python
from fastmcp import FastMCP, Context
from pydantic import BaseModel

mcp = FastMCP("my-mcp-server")

class Echo(BaseModel):
    message: str
    length: int

@mcp.tool
async def echo(message: str, ctx: Context) -> Echo:
    """Echo a message back with its length. Use for connectivity checks."""
    await ctx.info(f"echo: {message[:40]}")
    return Echo(message=message, length=len(message))

def main() -> None:
    mcp.run()   # stdio

if __name__ == "__main__":
    main()
```

**`skills/using-my-tools/SKILL.md`:**
```markdown
---
name: using-my-tools
description: >
  Use when the user needs to run X operations via the my-tools MCP server.
  Explains available tools (echo, ...) and when to prefer them over manual work.
allowed-tools: Read, Grep
---
# Using my-tools
When the task involves X, call the `echo` tool from the my-tools MCP server
instead of computing by hand. For details on parameters, see references/api.md.
```

**`tests/test_server.py`:**
```python
import pytest
from fastmcp import Client
from my_mcp_server.server import mcp

@pytest.mark.asyncio
async def test_echo():
    async with Client(mcp) as client:
        res = await client.call_tool("echo", {"message": "hi"})
        assert res.data["length"] == 2
```

**`.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: server } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run mypy src
      - run: uv run pytest -q
  publish:
    needs: test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: server } }
    permissions: { id-token: write }       # PyPI Trusted Publishing (OIDC)
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - run: uv publish            # без токена при Trusted Publishing
```

**Создание репо и публикация (gh CLI):**
```bash
gh repo create my-superplugin --public --source=. --remote=origin --push
# первый релиз/публикация
cd server && uv build && uv publish        # → PyPI (или настроить Trusted Publishing)
git tag v0.1.0 && git push origin v0.1.0   # триггерит publish-job
# добавить маркетплейс в Claude Code и установить
# /plugin marketplace add you/my-superplugin
# /plugin install my-superplugin@my-marketplace
```
Локальная отладка до публикации: `claude --plugin-dir ./my-superplugin`, затем `/reload-plugins`, `claude plugin validate ./my-superplugin`, `claude --debug`.

---

## Recommendations

**Этап 0 — решение по архитектуре.** Стройте гибрид «MCP‑ядро (PyPI, uvx) + переносимые skills». Это единственный вариант, который одновременно даёт детерминизм (tools), переносимость (skills open standard + MCP), и чистую дистрибуцию. Не кладите тяжёлую логику в skills — она ест контекст.

**Этап 1 — MCP‑сервер.** `uv init --package`, `uv_build`, `fastmcp>=3.0.0,<4`, src‑layout, `project.scripts`. Пишите тулзы с Pydantic‑моделями возврата (structured output бесплатно), `Context` для логов/прогресса, `async def` + `lifespan` под ваш пул async SQLAlchemy/Redis. Покройте in‑memory тестами (`Client(mcp)`) — это самый высокоэффективный слой тестов. Порог перехода к HTTP‑транспорту: сервер нужен удалённо/нескольким пользователям → `mcp.http_app()` + `JWTVerifier`.

**Этап 2 — skills.** Пишите по открытому стандарту: обязательны `name`+`description` (description = что+КОГДА, с trigger‑словами — это главный фактор срабатывания). Тело < 500 строк, детали в `references/`, детерминированные операции — в `scripts/` или в MCP‑тулзы. Применяйте «documentation TDD» из `writing-skills`: тестируйте скилл на свежем агенте до релиза.

**Этап 3 — упаковка в Claude Code plugin.** `plugin.json` (только в `.claude-plugin/`), компоненты в корне, `.mcp.json` в плоском формате с `uvx my-mcp-server`. Проверяйте `claude plugin validate` + `claude --plugin-dir` перед публикацией.

**Этап 4 — переносимость.** Добавьте `AGENTS.md`; для не‑Claude агентов задокументируйте их конфиги MCP (таблица раздела 3). Опционально включите `SkillsProvider` в сервер, чтобы skills раздавались по MCP любому клиенту. Для тонких адаптеров копируйте паттерн superpowers (`.cursor-plugin/`, `.codex-plugin/`).

**Этап 5 — CI/CD и версии.** GitHub Actions: ruff + mypy + pytest на PR; publish в PyPI по тегу (Trusted Publishing/OIDC — без хранения токена). Синхронизируйте `plugin.json.version` и `pyproject.toml.version`. Коммитьте `uv.lock`.

**Триггеры смены решений:**
- Тулзов > 20–25 → точность выбора тулза моделью падает; разбейте на несколько focused MCP‑серверов (Anthropic рекомендует < 20 тулзов на сервер).
- Нужен remote/мультиюзер → streamable HTTP + JWT + Docker + reverse proxy (TLS).
- Codex как таргет + HTTP → нужен `mcp-proxy` (Codex не умеет streamable HTTP напрямую).
- Нужны build‑hooks/VCS‑версии → смените `uv_build` на `hatchling`.

---

## Caveats

- **Число skills в ядре superpowers — ровно 14** (по стандарту agentskills.io); маркетинговые «20+» включают связанные плагины маркетплейса. Версия v6.1.1 подтверждена страницей Releases (02 июля 2026).
- **Путаница в доках Claude Code про `.mcp.json`:** официальный пример ошибочно показывает обёртку `mcpServers` внутри `.mcp.json`; по факту всех официальных плагинов Anthropic формат плоский (есть открытый issue #63694). Проверяйте на реальных примерах из `anthropics/claude-plugins-official`.
- **Официальная JSON‑схема маркетплейса:** ссылка `anthropic.com/claude-code/marketplace.schema.json` в официальных marketplace.json фактически не резолвится (по сообщениям сообщества) — это скорее артефакт. Поле `version` маркетплейса нигде не используется.
- **FastMCP auth‑классы мигрировали между релизами** — имена (`JWTVerifier` и т.п.) актуальны на 3.4.x, но исторически менялись; сверяйте с gofastmcp.com на момент внедрения.
- **uvx‑пример плагина (ToolUniverse):** JSON приведён по официальной документации проекта, не из raw‑файла репо — высокая достоверность, но формально не верифицировано на уровне файла. В `anthropics/claude-plugins-official` подтверждённые примеры MCP преимущественно на `npx`; uvx‑паттерн валиден и поддерживается, но менее распространён в самом официальном каталоге.
- **`fastmcp.json` vs `mcp.json`:** это разные вещи — `mcp.json` говорит клиенту КАК подключиться к серверу; `fastmcp.json` — декларативная конфигурация ЗАПУСКА сервера. Не путайте.
- **SkillsProvider / SEP‑2640 (skills over MCP)** — молодая фича v3; на практике не все клиенты авто‑подхватывают skills‑ресурсы (напр., есть сообщения о проблемах с GitHub Copilot в VS Code). Рассматривайте как дополнение, а не единственный канал доставки skills.
- **Даты и «свежесть»:** ряд фактов (v6.1.1, FastMCP 3.4.4 от 9 июля 2026, GA 18 фев 2026) верны на момент исследования (17 июля 2026); экосистема меняется быстро — сверяйте версии перед стартом проекта.