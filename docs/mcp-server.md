# MCP-сервер

Сервер `avito` — Python-пакет [`avito-mcp-server`](../server/README.md) на
[FastMCP v3](https://gofastmcp.com). Несёт весь **движок парсинга**
(полнофункциональный парсер каталога Avito): провайдеры кук и прокси,
HTTP-клиент на `curl_cffi`, извлечение JSON со страницы, фильтры, sqlite-хранилище,
экспорт и уведомления.

> **СТАТУС:** целевой дизайн — полнофункциональный парсер каталога Avito, полный
> контекст в
> [спеке дизайна](superpowers/specs/2026-07-18-avito-parser-design.md). Все 7 тулз
> и модули движка (`cookies/` `proxies/` `http/` `parser.py` `filters/` `storage/`
> `export/` `notifications/`) — **🔜 план, код ещё не написан**. Работает раздача
> `skills/` по MCP (`skills_provider.py`) и каркас in-memory тестов. Ниже —
> архитектура и конвенции.

## Стек

- Python ≥ 3.12, менеджер — `uv`
- `fastmcp>=3.0.0,<4`
- Сборка — `uv_build` (src-layout), публикация — PyPI
- Тесты — in-memory `Client(mcp)` + `pytest`

## Устройство тулз

```python
from fastmcp import FastMCP, Context
from pydantic import BaseModel

mcp = FastMCP("avito-mcp-server")

class Listing(BaseModel):
    id: int
    title: str
    price: float | None
    url: str | None
    address: str | None
    views: int | None = None          # только если with_views / parse_views

@mcp.tool
async def get_listing(id_or_url: str, ctx: Context, with_views: bool = False) -> Listing:
    """Детали объявления по id или URL. Use when нужны поля одного объявления."""
    await ctx.info(f"fetch {id_or_url}")
    # движок парсинга: провайдер кук → rotate-until-clean прокси
    #   → curl_cffi (impersonate) + follow SSR-редиректа
    #   → find_json_on_page → loaderData.data.catalog
    return Listing(id=..., title=..., price=..., url=..., address=...)
```

Конвенции:

- **Structured output** — возвращай Pydantic-модель; FastMCP сам сформирует
  `structuredContent` + текстовый блок. Схема генерится из аннотации возврата.
- **`Context`** — параметр с типом `Context` исключается из схемы; даёт
  `ctx.info/report_progress/elicit/read_resource`, `await ctx.set_state/get_state`.
- **`async def`** — под async-IO (HTTP, БД, Redis); `lifespan` — для пулов.
- **Docstring** = описание тулзы для модели: пиши «что делает + когда вызывать».
- **< 20 тулз на сервер** — иначе точность выбора тулзы моделью падает
  (рекомендация Anthropic); при росте — дели на focused-серверы.

## Тулзы

7 тулз — целевой полный фичесет парсинга Avito, все со статусом **🔜 план**.

| # | Тулза | Назначение | Статус |
| --- | --- | --- | --- |
| 1 | `search_listings` | Разовый поиск каталога по запросу/URL, региону, фильтрам | 🔜 план |
| 2 | `get_listing` | Детали одного объявления (`id_or_url`, `with_views`) | 🔜 план |
| 3 | `scan_new_listings` | Dedup + отслеживание смены цены (мониторинг-примитив, sqlite) | 🔜 план |
| 4 | `check_proxy_health` | Диагностика прокси и ротации-до-чистого | 🔜 план |
| 5 | `send_notification` | Уведомление в Telegram/VK | 🔜 план |
| 6 | `export_listings` | Экспорт объявлений в xlsx/json/csv | 🔜 план |
| 7 | `get_price_history` | История цены объявления из sqlite | 🔜 план |

Регистрация — через модули `server/src/avito_mcp_server/tools/*` с функцией
`register(mcp)`; `server.py` вызывает их для каждой группы тулз (по группе на модуль).

Фильтры (`include_keywords`, `exclude_keywords`, `seller_blacklist`,
`price_min/max`, `geo`, `max_age`) и `parse_views` — это **параметры** тулз, а не
отдельные тулзы: так набор держится глубоко под лимитом Anthropic «< 20 тулз».
Тулза `parse_phone` **не портируется** — сбор телефонов продавцов (ПДн
третьих лиц) исключён из фичесета. Возврат — Pydantic-модели (structured output),
ошибки наружу — через `ToolError`. Движок парсинга описан в
[§ Движок парсинга](#движок-парсинга-провайдеры) ниже и в скиле
[`scraping-avito`](../skills/scraping-avito/SKILL.md).

## Движок парсинга: провайдеры

Внутренняя структура `server/src/avito_mcp_server/` включает модули:
`cookies/` `proxies/` `http/` `export/` `notifications/` `filters/`
`storage/` + `models.py` + `parser.py` + `tools/`. Поток обработки одного запроса:

```text
провайдер кук → rotate-until-clean прокси → curl_cffi (impersonate)
  → follow SSR-редиректа на канонический URL категории
  → find_json_on_page (script[type=mime/invalid][data-mfe-state=true])
  → loaderData.data.catalog.items → фильтры → модели Listing
```

### Куки (`AVITO_COOKIE_PROVIDER`, дефолт `spfa`)

- `spfa` — `POST spfa.ru/api/cookies` + `/unblock` (валидировано живьём). Ключ
  `SPFA_API_KEY`.
- `own` — куки пользователя (`AVITO_OWN_COOKIES`).
- `playwright` — браузерная добыча (куки `ft`), опционально, тяжёлая extra-зависимость.

Единый интерфейс `CookiesProvider.get()/update()/handle_block()`.

### Прокси (`AVITO_PROXY` + опц. `AVITO_PROXY_CHANGE_URL`)

- `MobileProxy` (есть change-url → ротация) / `ServerProxy` (статик) / `NoProxy`.
- Формат `user:pass@host:port`.

### HTTP (`curl_cffi`)

`impersonate` ∈ {chrome, edge, safari}, случайный UA, прокси, follow-редирект,
`find_json_on_page`. **Наше улучшение retry-логики:** вместо одной ротации IP —
**rotate-until-clean** (до `AVITO_MAX_ROTATE_ATTEMPTS`, дефолт 18); это чинит
типичный дефект наивной retry-логики (одна ротация → сдача) на смешанном пуле.

### Переменные окружения

Сервер **не** читает `.env` (нет `load_dotenv`) — env передаёт шелл/агент.

| Переменная | Назначение |
| --- | --- |
| `SPFA_API_KEY` | ключ spfa (провайдер кук) |
| `AVITO_COOKIE_PROVIDER` | `spfa`\|`own`\|`playwright` (дефолт `spfa`) |
| `AVITO_OWN_COOKIES` | куки для провайдера `own` |
| `AVITO_PROXY` | `user:pass@host:port` |
| `AVITO_PROXY_CHANGE_URL` | URL ротации IP (→ `MobileProxy`) |
| `AVITO_TG_TOKEN`, `AVITO_TG_CHAT_IDS` | Telegram-уведомления |
| `AVITO_VK_TOKEN`, `AVITO_VK_USER_IDS` | VK-уведомления |
| `AVITO_DB_PATH` | путь sqlite (dedup + история цены) |
| `AVITO_MAX_ROTATE_ATTEMPTS` | лимит ротаций (дефолт 18) |
| `AVITO_SKILLS_DIR`, `CLAUDE_PLUGIN_ROOT` | резолв каталога `skills/` |

## Тестирование (in-memory)

```python
from fastmcp import Client
from avito_mcp_server.server import mcp

async def test_get_listing():                    # asyncio_mode="auto" → без декоратора
    async with Client(mcp) as client:            # без сети/субпроцесса
        res = await client.call_tool("get_listing", {"id_or_url": "..."})
        assert res.data.id == 123                # res.data — десериализованный объект (Listing)
        assert res.structured_content["id"] == 123   # dict-форма structured content
```

Сетевую границу движка (`curl_cffi`) мокай через подменяемый транспорт, HTML —
из фикстур живой страницы; фабрики провайдеров подменяй `monkeypatch`.

> Проверено на `fastmcp 3.4.4`: при возврате Pydantic-модели `res.data` —
> объект (доступ через атрибут), а `res.structured_content` — dict.

Это самый высокоэффективный слой тестов. Интеграционные (HTTP-транспорт, реальные
запросы) помечай `@pytest.mark.integration`.

## Транспорты и дистрибуция

- **stdio** (дефолт) — для локального плагина; так работает `.mcp.json`.
- **streamable HTTP** — `mcp.run(transport="http", host=..., port=...)` — если
  сервер нужен удалённо/нескольким пользователям (добавь `JWTVerifier`).

Три режима запуска клиентом (см. [`../server/README.md`](../server/README.md)):

```jsonc
{ "command": "uv",  "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/server", "avito-mcp-server"] } // dev
{ "command": "uvx", "args": ["--from", "git+https://github.com/evgenygurin/avito-mcp-plugin.git#subdirectory=server", "avito-mcp-server"] } // git
{ "command": "uvx", "args": ["avito-mcp-server"] } // PyPI
```

## Раздача skills по MCP

Сервер раздаёт каталог `skills/` как MCP-ресурсы (`skill://<name>/SKILL.md` и
`skill://<name>/_manifest`) через FastMCP `SkillsProvider` — любой MCP-клиент
получает те же `SKILL.md` через `list_resources` / `read_resource`.

Реализация — [`skills_provider.py`](../server/src/avito_mcp_server/skills_provider.py):
`register_skills(mcp)` разрешает путь из `AVITO_SKILLS_DIR` →
`${CLAUDE_PLUGIN_ROOT}/skills` → каталог репозитория; при отсутствии каталога
сервер работает без раздачи (graceful). Caveat: не все клиенты авто-подхватывают
skill-ресурсы — это дополнение к нативному skill-discovery, не единственный канал.

## Дальше

- Техника парсинга (движок, что реализуют тулзы) → [`avito-scraping.md`](avito-scraping.md)
- Целевой дизайн парсера → [спека дизайна парсера](superpowers/specs/2026-07-18-avito-parser-design.md)
- Список тулз для агента → скил [`using-avito-mcp`](../skills/using-avito-mcp/SKILL.md)
