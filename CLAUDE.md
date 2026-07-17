# avito-mcp-plugin — инструкции для AI-агентов

Прочитай это перед работой в репозитории.

## Что это

Переносимый плагин для AI-агентов: **skills + встроенный MCP-сервер** (FastMCP v3)
для работы с Avito. Архитектура — «толстое ядро + тонкие адаптеры». Полный
контекст: [`docs/architecture.md`](docs/architecture.md).

**Стадия — v0.1.0.** Реализованы: тулзы `ping` и `official_api_call`, OAuth2-клиент
официального API, доменные модели, утилита `extract_listing_id`, раздача `skills/`
по MCP (`SkillsProvider`) — 32 теста, ruff + mypy чисты. **Не написаны** только
парсинг-тулзы (`search_listings`, `get_listing`, `check_proxy_health`).
Статус скилов — в [`docs/skills.md`](docs/skills.md); план — в [`docs/roadmap.md`](docs/roadmap.md).

## Guardrails (обязательно)

Проект работает с парсингом Avito — это зона правового риска в РФ. При любой
реализации сбора данных:

- **Не реализуй «лобовой» обход капчи** (решение hCaptcha/GeeTest) — это смещает
  правовую квалификацию к ст. 272 УК. Стратегия проекта — **избегать** капчи
  чистыми RU-прокси, а не решать её.
- **Не собирай персональные данные** (телефоны, имена продавцов) для перепродажи —
  152-ФЗ. По умолчанию — только фактические поля (цена, характеристики).
- **Не копируй существенную долю БД** — ст. 1334 ГК. Парсинг инкрементальный.
- Детали — [`docs/avito-legal.md`](docs/avito-legal.md) и скил
  [`avito-legal-guardrails`](skills/avito-legal-guardrails/SKILL.md).

Секреты (client_secret официального API, прокси-креды) — только через переменные
окружения. Не хардкодить, не логировать, не коммитить.

## Переменные окружения

Сервер **не** подгружает `.env` (нет `load_dotenv`) — переменные передаёт шелл/агент.
Образец — [`.env.example`](.env.example).

| Переменная | Назначение | Обязательна |
|---|---|---|
| `AVITO_CLIENT_ID`, `AVITO_CLIENT_SECRET` | официальный API (`official_api_call`); `from_env()` кидает `ValueError`, если пусто | для официального API |
| `CLAUDE_PLUGIN_ROOT` | резолв `skills/` при установке плагина (`${CLAUDE_PLUGIN_ROOT}/skills`) | нет |
| `AVITO_SKILLS_DIR` | явный override каталога skills | нет |
| `LOG_LEVEL` | объявлена в `.env.example`, но **пока нигде не читается** (аспирационная) | нет |

## Структура

- В `.claude-plugin/` лежат **`plugin.json` и `marketplace.json`** — и только они.
  Все остальные компоненты (`skills/`, `.mcp.json`, `server/`, …) — в корне.
  Положишь `skills/` внутрь `.claude-plugin/` — тихий провал (не загрузятся).
- `.mcp.json` — **плоский формат** (ключ = имя сервера на верхнем уровне, без
  обёртки `mcpServers`); использует локальный запуск `uv run --project`.
- **Переносимый слой:** `gemini-extension.json` (+`GEMINI.md`), `.cursor-plugin/plugin.json`,
  `.codex/INSTALL.md`, готовые конфиги `examples/mcp-configs/` (Cursor/Codex/Gemini/VS Code).
  Обзор — [`docs/portability.md`](docs/portability.md).

## Команды

```bash
# MCP-сервер (всё из каталога server/):
cd server
uv sync --dev
uv run avito-mcp-server   # запуск по stdio (проверка, что сервер поднимается)
uv run pytest -q          # 32 теста, in-memory Client(mcp)
uv run ruff check .
uv run mypy src

# Из корня репозитория:
python3 scripts/check_versions.py   # синхронность версий в 5 манифестах (голый python3, не uv)
claude plugin validate ./           # валидация манифестов плагина
```

Релиз/публикация (`uv build` / `uv publish` / тег) — [`docs/releasing.md`](docs/releasing.md).
CI пока нет.

## Изменение MCP-сервера

Пакет в [`server/`](server/README.md), src-layout, `uv`, Python ≥ 3.12,
`fastmcp>=3,<4`, `httpx>=0.27`.

Модули `server/src/avito_mcp_server/`: `server.py` (инстанс + `main()` + регистрация),
`models.py` (Pydantic-модели — заготовка под listings, **тулзами пока не используются**),
`utils.py`, `official_api.py` (OAuth2-клиент, инъекция `httpx.AsyncClient`),
`skills_provider.py`, `tools/official_api.py`.

- **Паттерн расширения:** новая группа тулз — модуль `tools/<name>.py` с функцией
  `register(mcp)`, которую `server.py` вызывает явно. Не только `@mcp.tool` в `server.py`.
- Тулзы: `async def`, `Context` для логов/прогресса, docstring = «что делает + когда
  вызывать». Возврат — Pydantic-модель (structured output) **или** `dict[str, Any]`
  для сырого JSON API (как `official_api_call`). Ошибки наружу — через `ToolError`.
- < 20 тулз на сервер (иначе падает точность выбора моделью). Сейчас их 2.

**Тесты** (`server/tests/`, `asyncio_mode="auto"` → async-тесты без декоратора):
in-memory `Client(mcp)`; сетевая граница мокается через `httpx.MockTransport`
(мок транспорта, не методов клиента); фабрики подменяются `monkeypatch`. Новый код —
по TDD (`superpowers:test-driven-development`).

## Раздача skills по MCP

`skills_provider.py` раздаёт `skills/` как MCP-ресурсы (`skill://<name>/SKILL.md`)
через `SkillsProvider`. `register_skills(mcp)` резолвит путь: `AVITO_SKILLS_DIR` →
`${CLAUDE_PLUGIN_ROOT}/skills` → каталог репозитория; при отсутствии — сервер
работает без раздачи (graceful, `return False`).

## Изменение skills

Skills — это не проза, а код, формирующий поведение агента. Меняй их по
методологии `superpowers:writing-skills`:

- `description` описывает **КОГДА** применять (триггеры, симптомы, ключевые слова),
  а не пересказывает workflow;
- тело < 500 строк; тяжёлые детали — в `references/` (пока их нет — все скилы
  одиночные `SKILL.md`), детерминированные операции — в тулзы;
- перед релизом — RED→GREEN→REFACTOR на субагентах.

Статус скилов зафиксирован в [`docs/skills.md`](docs/skills.md) (не в телах SKILL.md).

## Документация зависимостей — Context7 (обязательно)

Перед тем как писать или менять код, использующий **FastMCP** или любую другую
Python-зависимость, **сначала сверься с актуальной документацией через Context7**
под ту версию, что реально стоит в проекте. Не полагайся на память, обучающие
данные или `docs/researches/` — API меняется между версиями.

Проверить установленную версию:

```bash
cd server && uv run python -c "import fastmcp; print(fastmcp.__version__)"
```

Затем (workflow Context7 из глобального `~/.claude/CLAUDE.md`):

1. `resolve-library-id(libraryName: "fastmcp")` → получить Context7 ID.
2. `query-docs(id, topic: "<tools|context|structured-output|auth|testing|...>", mode: "code")`
   — `topic` **обязателен**; `mode=code` для примеров, `mode=info` для архитектуры.

**Почему это критично:** FastMCP v3 имел breaking changes относительно v2, а
детали отличаются даже между 3.x. Пример: в `fastmcp 3.4.4` `res.data` —
десериализованный объект (`res.data.length`), а не dict (`res.data["length"]`).
Так же сверяй API `pydantic`, `uv`, `httpx`/`curl_cffi` с версией из `uv.lock`.

## Версии

SemVer синхронно в **пяти** манифестах: `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `server/pyproject.toml`, `gemini-extension.json`,
`.cursor-plugin/plugin.json`. При бампе меняй все пять и проверь
`python3 scripts/check_versions.py` (exit 0 = синхронны).

## Gotchas

- **`.env` не читается автоматически** — нет `load_dotenv`; передавай env через шелл.
- **`LOG_LEVEL` мёртвая** — объявлена в `.env.example`, но сервер её не читает.
- **`AVITO_SKILLS_DIR`**: если путь задан, но не каталог → раздача skills молча
  отключается (fallback на `CLAUDE_PLUGIN_ROOT` **не** срабатывает при override).
- **`models.py`** реализованы и покрыты тестами, но ни одной тулзой не используются
  (заготовка под listings).
- **`official_api_call`** не ограничивает `method`/`path` — guardrail «только свои
  объявления» держится на docstring, не на коде.
- **Токен официального API** кэшируется без учёта `expires_in`; смягчено тем, что
  тулза создаёт новый клиент на каждый вызов и закрывает его в `finally`.
- **Локальная установка плагина** (`claude plugin marketplace add <локальный путь>`)
  копирует каталог целиком, включая gitignored `server/.venv` и кэши. Битый
  скопированный `.venv` роняет MCP-сервер («no Python executable»). Перед локальной
  установкой удали `server/.venv`, либо ставь из git/PyPI (git исключает эти файлы).
  Проверено: после очистки `.venv` в кэше плагин поднимает сервер и тулзы штатно.

## Git

Следуй глобальным правилам (`~/.claude/rules/git.md`): Conventional Commits,
явный `git add <файлы>` (не `git add .`), атомарные коммиты, без force-push в main.
Глобальный gitignore игнорирует `CLAUDE.md`/`GEMINI.md`/`.mcp.json`/`uv.lock` —
для них нужен `git add -f`.
