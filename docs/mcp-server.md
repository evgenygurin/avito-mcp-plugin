# MCP-сервер

Сервер `avito` — Python-пакет [`avito-mcp-server`](../server/README.md) на
[FastMCP v3](https://gofastmcp.com). Несёт всю детерминированную логику: HTTP к
Avito, парсинг, официальный API, работу с прокси.

> **СТАТУС:** реализованы `ping`, клиент официального API и тулза
> `official_api_call`, доменные модели и утилиты (26 тестов, ruff + mypy чисты).
> Парсинг-тулзы — в разработке. Ниже — архитектура и конвенции.

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

@mcp.tool
async def get_listing(id_or_url: str, ctx: Context) -> Listing:
    """Детали объявления по id или URL. Use when нужны поля одного объявления."""
    await ctx.info(f"fetch {id_or_url}")
    ...  # гибридная схема: куки+прокси → m.avito.ru/api/*
    return Listing(id=..., title=..., price=...)
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

| Тулза | Назначение | Скил | Статус |
|---|---|---|---|
| `ping` | Диагностика связи | — | ✅ готово |
| `official_api_call` | Официальный API (свои объявления) | `avito-official-api` | ✅ готово |
| `search_listings` | Поиск объявлений по запросу/региону/фильтрам | `scraping-avito` | 🔜 план |
| `get_listing` | Детали объявления | `scraping-avito` | 🔜 план |
| `check_proxy_health` | Диагностика прокси-пула | `scraping-avito` | 🔜 план |

Регистрация — через модули `server/src/avito_mcp_server/tools/*` с функцией
`register(mcp)`; `server.py` вызывает их для каждой группы тулз.

Парсинг-тулзы требуют слоя обхода антибота (браузер + прокси) и **не**
реализуют «лобовой» обход капчи — см. [`avito-legal.md`](avito-legal.md) и
скил [`scraping-avito`](../skills/scraping-avito/SKILL.md).

## Тестирование (in-memory)

```python
import pytest
from fastmcp import Client
from avito_mcp_server.server import mcp

@pytest.mark.asyncio
async def test_ping():
    async with Client(mcp) as client:          # без сети/субпроцесса
        res = await client.call_tool("ping", {"message": "hi"})
        assert res.data.length == 2            # res.data — десериализованный объект
        assert res.structured_content["length"] == 2   # dict-форма structured content
```

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

## Раздача skills по MCP (опционально)

FastMCP v3 `SkillsProvider` умеет выставлять директорию `skills/` как
MCP-ресурсы (`skill://`), чтобы те же `SKILL.md` получал любой MCP-клиент
(SEP-2640). Фича молодая — рассматривать как дополнение, не единственный канал.

## Дальше

- Техника парсинга (что реализуют тулзы) → [`avito-scraping.md`](avito-scraping.md)
- Официальный API → [`avito-scraping.md`](avito-scraping.md) (§ Официальный API)
- Правовые ограничения → [`avito-legal.md`](avito-legal.md)
