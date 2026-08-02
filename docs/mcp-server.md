# MCP-серверы

После Фаз 2–5 плагин состоит из **uv-workspace `servers/` с ролевыми
MCP-серверами** на [FastMCP v3](https://gofastmcp.com). Единственная точка
входа для клиента — **gateway** (см. [`.mcp.json`](../.mcp.json)); ролевые
серверы подтягиваются им как Python-пакеты. Каждый сервер можно поднять и
проверить и по отдельности.

## Состав

| Каталог | Пакет | Роль | pipeline |
|---|---|---|---|
| `servers/gateway` | `avito_mcp_server` | входная дверь: 7 тулз + skills по MCP + прокси db/notify | `avito-mcp-server` |
| `servers/scraper` | `avito_mcp_scraper` | движок парсинга (stateless): search/get/check | `avito-mcp-scraper` |
| `servers/db` | `avito_mcp_db` | единственный stateful: Supabase, история, экспорт | `avito-mcp-db` |
| `servers/notify` | `avito_mcp_notify` | уведомления Telegram/VK | `avito-mcp-notify` |
| `servers/shared` | `avito_mcp_shared` | общие утилиты (роли, неймспейсы) | — |

## Запуск (каждый сервер отдельно)

Рабочий корень — uv-workspace `servers/`; зависимости ставятся из любого
каталога-члена. Сервер стартует по stdio на дефолтном транспорте.

```bash
cd servers/gateway && uv sync --dev && uv run python -m avito_mcp_server
cd servers/scraper && uv sync --dev && uv run python -m avito_mcp_scraper
cd servers/db      && uv sync --dev && uv run python -m avito_mcp_db
cd servers/notify  && uv sync --dev && uv run python -m avito_mcp_notify
```

То же через console-скрипт: `uv run avito-mcp-server` (и `-scraper`, `-db`,
`-notify`). Каждый сервер запускается **сам по себе** — его `pyproject`
несёт только свои зависимости; совместная композиция происходит в gateway
импортом.

## Проверки (на сервер, из его каталога)

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
```

`shared` — тесты ролей/неймспейсов; тесты хранилища db пропускаются без
`AVITO_SUPABASE_DSN` (живой Postgres). Общий замок — `servers/uv.lock`
(uv-workspace). Синхронность версий — `python3 scripts/check_versions.py`
(exit 0).

## Стек

- Python ≥ 3.12, менеджер — `uv`
- `fastmcp>=3.0.0,<4`, сборка — `uv_build` (src-layout)
- Тесты — in-memory `Client(mcp)` + `pytest` (`asyncio_mode="auto"`)

## Устройство тулз

Тулза — `async def` с аннотацией возврата (Pydantic-модель) и параметром
`ctx: Context` (исключается из схемы). Конвенции:

- **Structured output** — FastMCP сам формирует `structuredContent` + текст.
- **Docstring** = описание тулзы для модели: «что делает + когда вызывать».
- **< 20 тулз на сервер** — иначе точность выбора падает; при росте — дели
  на focused-серверы.
- **Destructive-аннотации** для side-effect тулз (`export_listings`,
  `send_notification` — `destructiveHint`); чтения — `readOnlyHint`.

Регистрация — через `register(mcp)` в модулях `.../tools/*`; `server.py`
вызывает их для каждой группы тулз. `scan_new_listings` в gateway
собирает каталог через scraper и делегирует персистент в db (`persist_scan`)
— это стыковка «scan → db» внутри gateway.

## 7 MCP-тулз (реализованы)

| # | Тулза | Назначение | Владелец |
|---|---|---|---|
| 1 | `search_listings` | поиск каталога (фильтры, `pages`) | scraper |
| 2 | `get_listing` | детали объявления (`id_or_url`, `with_views`) | scraper |
| 3 | `check_proxy_health` | диагностика: каждый адрес пула (`probes`) | scraper |
| 4 | `scan_new_listings` | dedup + отслеживание цены (мониторинг) | gateway+scraper+db |
| 5 | `get_price_history` | история цены из Postgres | db |
| 6 | `export_listings` | экспорт в xlsx/json/csv | db |
| 7 | `send_notification` | уведомление Telegram/VK | notify |

Фильтры (`include_keywords`, `exclude_keywords`, `seller_blacklist`,
`price_min/max`, `geo`, `max_age`) и `pages` — параметры тулз, не отдельные
тулзы. `parse_phone` не портируется (ПДн третьих лиц). Возврат — Pydantic
(structured output), ошибки — `ToolError`. Движок — в
[`avito-scraping.md`](avito-scraping.md) и в скиле
[`scraping-avito`](../skills/scraping-avito/SKILL.md).

## Переменные окружения

Серверы **не** читают `.env` — env передаёт шелл/агент.

| Переменная | Назначение |
|---|---|
| `SPFA_API_KEY` | ключ spfa (провайдер кук) |
| `AVITO_COOKIE_PROVIDER` | `spfa`\|`own`\|`playwright` (дефолт `spfa`) |
| `AVITO_OWN_COOKIES` | куки для провайдера `own` |
| `AVITO_PROXY` | `user:pass@host:port` (список через запятую) |
| `AVITO_PROXY_CHANGE_URL` | URL ротации IP (→ `MobileProxy`) |
| `AVITO_SUPABASE_DSN` | Postgres проекта Supabase (db: dedup + история + cooldown) |
| `AVITO_TG_TOKEN`, `AVITO_TG_CHAT_IDS` | Telegram-уведомления (notify) |
| `AVITO_VK_TOKEN`, `AVITO_VK_USER_IDS` | VK-уведомления (notify) |
| `AVITO_MAX_ROTATE_ATTEMPTS` | лимит перебора комбинаций (дефолт 12) |
| `AVITO_ROTATE_WAIT` | старт: пауза после смены IP, сек (дефолт 3.0) |
| `AVITO_REQUEST_BUDGET` | потолок времени на клиента, сек |
| `LOG_LEVEL` | уровень логов (дефолт `INFO`), stderr |
| `AVITO_LOG_FILE` | дублировать логи в файл |
| `AVITO_SKILLS_DIR`, `CLAUDE_PLUGIN_ROOT` | резолв каталога `skills/` |

## Наблюдаемость

Логи в stderr (stdout занят JSON-RPC при stdio). Каждый вызов тулзы
заканчивается сводкой фаз:

```text
check_proxy_health total=81.682s backoff.sleep=54.009s×4 proxy.rotate=21.263s×6 …
```

Дорогие операции — `timing.timed(...)`, длинные обходы отчитываются о прогрессе
(`progress.report`). Производительность: 95% времени вызова — ожидание (пауза
после блокировки + смена IP) — оптимизировать имеет смысл `AVITO_ROTATE_WAIT`
и `AVITO_MAX_ROTATE_ATTEMPTS`, а не код парсинга.

## Тестирование (in-memory)

```python
from fastmcp import Client
from avito_mcp_server.server import mcp

async def test_get_listing():                    # asyncio_mode="auto"
    async with Client(mcp) as client:            # без сети/субпроцесса
        res = await client.call_tool("get_listing", {"id_or_url": "..."})
        assert res.data.id == 123
        assert res.structured_content["id"] == 123
```

Сетевую границу (`curl_cffi`) мокай через подменяемый транспорт, HTML — из
фикстур; фабрики провайдеров — `monkeypatch`. Интеграционные помечай
`@pytest.mark.integration`. db-тесты хранилища против настоящего Postgres
(skip без DSN); тулзы db — на `FakeStorage`.

## Транспорты и дистрибуция

- **stdio** (дефолт) — для локального плагина; так работает `.mcp.json`.
- **streamable HTTP** — `mcp.run(transport="http", host=..., port=...)` для
  удалённого/мультиюзера (добавь `JWTVerifier`).

Клиент запускает только gateway (см. `.mcp.json`); ролевые серверы
подтягиваются им по uv-workspace. PyPI-конфиг каждого — в
`<server>/pyproject.toml` (`uvx`).

## Раздача skills по MCP

Gateway раздаёт каталог `skills/` как MCP-ресурсы
(`skill://<name>/SKILL.md`) через `SkillsProvider` —
[`skills_provider.py`](../servers/gateway/src/avito_mcp_server/skills_provider.py).
Путь: `AVITO_SKILLS_DIR` → `${CLAUDE_PLUGIN_ROOT}/skills` → каталог
репозитория; при отсутствии — сервер работает без раздачи (graceful).

## Дальше

- Архитектура (композиция) → [`architecture.md`](architecture.md)
- Техника парсинга → [`avito-scraping.md`](avito-scraping.md)
- Список тулз для агента → скил [`using-avito-mcp`](../skills/using-avito-mcp/SKILL.md)