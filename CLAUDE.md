# avito-mcp-plugin — инструкции для AI-агентов

Прочитай это перед работой в репозитории.

## Что это

Переносимый плагин для AI-агентов: **skills + встроенный MCP-сервер** (FastMCP v3)
для работы с Avito. Цель — **полнофункциональный парсер публичного каталога Avito**
(самостоятельный скрапер, не клон стороннего проекта). Поставка — **MCP-тулзы + skills**, без GUI
(агент = UI). Архитектура — «толстое ядро (движок парсинга) + тонкие адаптеры».
Полный контекст: [`docs/architecture.md`](docs/architecture.md); канон дизайна —
[`docs/superpowers/specs/2026-07-18-avito-parser-design.md`](docs/superpowers/specs/2026-07-18-avito-parser-design.md).

**Стадия — v0.1.0.** Движок парсинга воспроизведён и **валидирован живьём**:
провайдер кук (spfa) → **rotate-until-clean** (ротация IP до чистого) → curl_cffi
(`impersonate`) + follow SSR-редиректа на канонический URL → извлечение
`loaderData.data.catalog.items`. Раздача `skills/` по MCP (`SkillsProvider`) работает.

**7 MCP-тулз реализованы** (`search_listings`, `get_listing`, `scan_new_listings`,
`check_proxy_health`, `send_notification`, `export_listings`, `get_price_history`).
`ping`/`official_api_call` удалены вместе с официальным API (см. `docs/roadmap.md`,
«Линия A»). Сетевая часть **проверена живьём** (2026-07-19): `check_proxy_health`,
`search_listings` и `scan_new_listings` (dedup + история цены в Postgres) прошли
end-to-end на купленном RU-прокси (spfa + MobileProxy). С домашнего IP без прокси
Avito по-прежнему отдаёт 403/429 после 2–3 запросов — нужен `AVITO_PROXY`.
Статус скилов — в [`docs/skills.md`](docs/skills.md); план — в [`docs/roadmap.md`](docs/roadmap.md).

## Переменные окружения

Сервер **не** подгружает `.env` (нет `load_dotenv`) — переменные передаёт шелл/агент.
Образец — [`.env.example`](.env.example). Секреты (`SPFA_API_KEY`, прокси-креды,
токены Telegram/VK) — только через env: не хардкодить, не логировать, не коммитить.

| Переменная | Назначение |
|---|---|
| `SPFA_API_KEY` | ключ spfa (провайдер кук по умолчанию) |
| `AVITO_COOKIE_PROVIDER` | `spfa`\|`own`\|`playwright` (дефолт `spfa`) |
| `AVITO_OWN_COOKIES` | куки для провайдера `own` |
| `AVITO_PROXY` | прокси `user:pass@host:port`; **список через запятую → `ProxyPool`** |
| `AVITO_PROXY_CHANGE_URL` | URL ротации IP (→ MobileProxy) |
| `AVITO_PROXY_LIST_URL` | кабинет со списком прокси (JSON-массив или строки); недоступен → фоллбэк на `AVITO_PROXY` |
| `AVITO_COOKIES_CACHE` | файл кэша кук spfa (дефолт `~/.cache/avito-mcp-server/cookies.json`, TTL 12 ч) |
| `AVITO_PAGE_PAUSE` | пауза между страницами каталога, сек (дефолт 1.0) |
| `AVITO_TG_TOKEN`, `AVITO_TG_CHAT_IDS` | Telegram-уведомления |
| `AVITO_VK_TOKEN`, `AVITO_VK_USER_IDS` | VK-уведомления |
| `AVITO_SUPABASE_DSN` | DSN Postgres проекта Supabase — **единственное** хранилище |
| `AVITO_MAX_ROTATE_ATTEMPTS` | лимит ротаций IP (дефолт 18) |
| `AVITO_SKILLS_DIR` | явный override каталога skills |
| `CLAUDE_PLUGIN_ROOT` | резолв `skills/` при установке плагина (`${CLAUDE_PLUGIN_ROOT}/skills`) |
| `LOG_LEVEL` | объявлена в `.env.example`, но **пока нигде не читается** (аспирационная) |

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
uv run pytest -q          # in-memory Client(mcp)
uv run ruff check .
uv run mypy src

# Из корня репозитория:
python3 scripts/check_versions.py   # синхронность версий в 5 манифестах (голый python3, не uv)
claude plugin validate ./ --strict  # ТОЛЬКО манифесты: marketplace.json + plugin.json.
# SKILL.md он здесь НЕ проверяет: marketplace root == plugin root, поэтому команда
# всегда уходит в marketplace-режим. Чтобы проверить скилы — копия репо без
# .claude-plugin/marketplace.json и `claude plugin validate <копия> --strict`
```

Релиз/публикация (`uv build` / `uv publish` / тег) — [`docs/releasing.md`](docs/releasing.md).
CI — [`.github/workflows/ci.yml`](.github/workflows/ci.yml) на push в `main`/`dev` и на
каждый PR: те же пять шагов (`ruff check`, `ruff format --check`, `mypy src`, `pytest`,
`scripts/check_versions.py`). Без `AVITO_SUPABASE_DSN` тесты хранилища скипаются —
воспроизвести локально: `env -u AVITO_SUPABASE_DSN uv run pytest -q`.

## Изменение MCP-сервера

Пакет в [`server/`](server/README.md), src-layout, `uv`, Python ≥ 3.12,
`fastmcp>=3,<4`, `httpx>=0.27` (движок парсинга — на `curl_cffi`).

Внутренняя структура `server/src/avito_mcp_server/` организована по модулям парсинга
(каждый модуль — со своей границей мока в тестах):

```text
avito_mcp_server/
├── cookies/       # провайдеры кук: spfa (дефолт) / own / playwright
├── proxies/       # Mobile/Server/None + ротация-до-чистого (rotate-until-clean)
├── http/          # curl_cffi клиент (impersonate, follow-редирект, retry)
├── export/        # xlsx / json / csv
├── notifications/ # Telegram, VK
├── filters/       # keyword/seller/price/geo/max_age
├── storage/       # models.py (ORM) + rows.py + base.py (Protocol) + supabase.py
├── models.py      # Listing / SearchResult (факты + опции)
├── parser/        # ядро: state.py (SSR-JSON + PageKind), mapping.py (→ Listing),
│                  #   pagination.py (обход каталога); фасад — parser/__init__.py
├── skills_provider.py  # раздача skills по MCP (остаётся)
├── tools/         # тонкий MCP-слой поверх ядра (register(mcp) на группу):
│                  #   catalog.py (общий обход) + execution.py (поток + ToolError)
└── server.py      # инстанс + main() + регистрация групп тулз
```

- **Паттерн расширения:** новая группа тулз — модуль `tools/<name>.py` с функцией
  `register(mcp)`, которую `server.py` вызывает явно. Не только `@mcp.tool` в `server.py`.
- Тулзы: `async def`, `Context` для логов/прогресса, docstring = «что делает + когда
  вызывать». Возврат — Pydantic-модель (structured output, напр. `SearchResult`).
  Ошибки наружу — через `ToolError`.
- < 20 тулз на сервер (иначе падает точность выбора моделью). Сейчас 7
  (+ раздача skills по MCP как ресурсы, не тулзы).
- Общее для всех тулз — в `tools/`: `execution.run_blocking()` (поток + единый
  `ToolError`) и `catalog.collect_listings()` (обход каталога + фильтры). Свой
  `asyncio.to_thread` + `try/except` в новой тулзе не пиши.
- Статус страницы — `parser.PageKind` (`StrEnum`), а не строковый литерал; сравнения
  вида `kind == "ok"` продолжают работать, но ветвиться лучше по членам enum.
- Расширяемые точки устроены реестрами, а не `if/elif`: `export.exporter._EXPORTERS`,
  `notifications.sender._NOTIFIERS`, `cookies.factory._PROVIDERS`,
  `filters.filters._CRITERIA`. Новый формат/канал/провайдер/критерий — запись в реестр.

**Тесты** (`server/tests/`, `asyncio_mode="auto"` → async-тесты без декоратора):
in-memory `Client(mcp)`; сетевая граница мокается через `httpx.MockTransport`
(мок транспорта, не методов клиента); фабрики подменяются `monkeypatch`. Новый код —
по TDD (`superpowers:test-driven-development`).

- Сетевая граница тулз поиска и мониторинга — одна: `tools/catalog.py`. Мокать надо
  `catalog_mod.fetch_catalog` / `build_http_client` (а не одноимённые в `tools/search.py`),
  поэтому общий обход `parser.walk_pages` принимает `fetch` аргументом. Там же зануляй
  `catalog_mod.page_pause`, иначе тесты реально спят.
- `res.data` у `Client(mcp)` — не Pydantic-модель; для проверки всего ответа целиком
  бери `res.structured_content`.
- Тулзы тестируются на `FakeStorage` из [`tests/fakes.py`](server/tests/fakes.py)
  (импорт `from fakes import FakeStorage` — пакета `tests` нет). Само хранилище —
  против **живого** Postgres, тесты пропускаются без `AVITO_SUPABASE_DSN`: подменять
  Postgres другой СУБД нельзя, диалектный upsert и `timestamptz` ведут себя иначе.

## Хранилище: только Postgres (Supabase)

**sqlite не используется нигде** — ни в коде, ни в тестах. Один бэкенд, один путь;
`AVITO_SUPABASE_DSN` обязателен для мониторинга и истории цен.

- ORM — **SQLAlchemy 2.0**: `DeclarativeBase`, аннотации `Mapped`/`mapped_column`,
  схема через `__table_args__ = {"schema": "avito"}` ([`storage/models.py`](server/src/avito_mcp_server/storage/models.py)).
- Upsert — диалектный `postgresql.insert(...).on_conflict_do_update()`; универсального
  бэкенд-агностик upsert в SQLAlchemy нет.
- DSN из кабинета (`postgresql://…`) нормализуется в `postgresql+psycopg://…`:
  иначе SQLAlchemy подставит psycopg2, которого в зависимостях нет.
- `sqlalchemy` + `psycopg[binary]` — **основные** зависимости, не extra.

- Проект Supabase: `avito-mcp-plugin`, ref `wvszgigxihuaaardchft`, eu-central-1.
  Миграции — в [`supabase/migrations/`](supabase/migrations/).
- Схема **`avito`**, не `public`, и она **закрыта от Data API** → ходим прямым
  подключением по DSN (`psycopg`), а не через REST/PostgREST.
- **RLS включён, политик нет — это замысел, а не недоделка:** доступ остаётся только
  у `service_role`, `anon`/`authenticated` отозваны. `get_advisors` показывает
  INFO `rls_enabled_no_policy` — ожидаемо, «чинить» не нужно.
- Наружу время отдаётся **epoch-float**, хотя в Postgres лежит `timestamptz` —
  иначе поедут модели тулз (`PricePoint` ждёт число).
- В `proxy_cooldown` пишется адрес **без учётных данных**; `mask_proxy()` режет
  `user:pass@` и в выводе `check_proxy_health`.

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
Python-зависимость (`pydantic`, `httpx`, `curl_cffi`, `uv`, `bs4`, `playwright`, …),
**ВСЕГДА СНАЧАЛА через Context7 изучи документацию, лучшие практики и идиомы под ту
версию, что реально стоит в проекте** — только так задача решается максимально
качественно и эффективно, а не «по памяти». Не полагайся на память, обучающие
данные или `docs/researches/` — и API, и рекомендации меняются между версиями.

Проверить установленную версию:

```bash
cd server && uv run python -c "import fastmcp; print(fastmcp.__version__)"
```

Затем (workflow Context7 из глобального `~/.claude/CLAUDE.md`):

1. `resolve-library-id(libraryName: "fastmcp")` → получить Context7 ID.
2. `query-docs(id, topic: "<tools|context|structured-output|auth|testing|...>", mode: "code")`
   — `topic` **обязателен**; `mode=code` для примеров, `mode=info` для архитектуры
   и лучших практик. Сначала сверься, потом пиши код.

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
- **Локальная установка плагина** (`claude plugin marketplace add <локальный путь>`)
  копирует каталог целиком, включая gitignored `server/.venv` и кэши. Битый
  скопированный `.venv` роняет MCP-сервер («no Python executable»). Перед локальной
  установкой удали `server/.venv`, либо ставь из git/PyPI (git исключает эти файлы).
  Проверено: после очистки `.venv` в кэше плагин поднимает сервер и тулзы штатно.
- **Кэш плагина живёт своей жизнью.** Правки в рабочем дереве не видны установленному
  плагину, пока не сделаешь `rsync` в `~/.claude/plugins/cache/.../server/src/` —
  а новые тулзы появятся только после перезапуска MCP-процесса (в non-interactive
  сессии он сам не респавнится). Для проверки кода без этого — in-memory `Client(mcp)`
  из рабочего дерева.
- **Долгие сетевые прогоны запускай фоном с логом в файл + `Monitor` на хвост.**
  `HttpClient.get` крутит до 18 попыток; без логов это выглядит как зависание.
- **Классификатор auto-режима блокирует внешние изменения** (пауза проекта Supabase,
  запуск парсинга). Не обходить — просить пользователя сделать это самому.
- **Supabase free-план: 2 активных проекта.** Статусы `RESTORING`/`PAUSING` считаются
  активными; приостановленные — нет. Тулзы удаления проекта в MCP нет вовсе.
- **Куки spfa стоят денег** (~12 ₽) и живут ~12 ч, а каждый вызов тулзы — новый
  процесс: без файлового кэша они покупались бы заново на каждом запросе.

## Git

Следуй глобальным правилам (`~/.claude/rules/git.md`): Conventional Commits,
явный `git add <файлы>` (не `git add .`), атомарные коммиты, без force-push в main.
Глобальный gitignore игнорирует `CLAUDE.md`/`GEMINI.md`/`.mcp.json`/`uv.lock` —
для них нужен `git add -f`.
