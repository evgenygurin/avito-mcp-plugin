# Phase 2 — Parsing MCP Tools Implementation Plan

> **For agentic workers:** implement task-by-task via TDD. Steps use checkbox syntax.

**Goal:** Обвязать движок Фазы 1 в MCP-тулзы: сборка движка из env (`config.py`),
тулза `search_listings` (каталог → факты → фильтры → `SearchResult`) и
`check_proxy_health`; регистрация в `server.py`.

**Architecture:** Тонкий async MCP-слой поверх синхронного движка. Блокирующие
вызовы curl_cffi оборачиваются в `asyncio.to_thread`. Возврат — Pydantic-модели
(structured output). Ошибки наружу — `ToolError`. FastMCP 3.4.4 (`@mcp.tool`,
`ctx: Context`, `await ctx.info`).

**Scope (осознанно):** одна страница каталога, без `parse_views`, вход — URL
каталога Avito. `get_listing` (детали объявления), пагинация `web/1/js/items`,
`parse_views`, query→URL — следующий заход (нужны фикстуры страницы объявления и
живой прогон).

**Tech Stack:** fastmcp 3.4.4, pydantic 2.13, asyncio, pytest (in-memory `Client(mcp)`).

---

### Task 1: `config.py` — сборка движка из env

**Files:** Create `server/src/avito_mcp_server/config.py`, `server/tests/test_config.py`

- [ ] Тест (monkeypatch env): `build_http_client()` при `AVITO_COOKIE_PROVIDER=own`
  + `AVITO_OWN_COOKIES` даёт `HttpClient` с `OwnCookiesProvider` и нужным proxy-типом;
  дефолт провайдера — `spfa` (требует `SPFA_API_KEY`, иначе `ValueError`).
- [ ] Реализация: `build_http_client() -> HttpClient` читает `AVITO_COOKIE_PROVIDER`
  (дефолт `spfa`), `SPFA_API_KEY`, `AVITO_OWN_COOKIES` (JSON или `k=v; k=v`),
  `AVITO_PROXY`, `AVITO_PROXY_CHANGE_URL`, `AVITO_MAX_ROTATE_ATTEMPTS` (дефолт 18);
  собирает через `build_cookies_provider` + `build_proxy`.
- [ ] pytest + ruff + mypy зелёные. Commit: `feat(config): assemble engine from env`.

---

### Task 2: `search_listings` тулза

**Files:** Create `server/src/avito_mcp_server/tools/search.py`, `server/tests/test_tools_search.py`

- [ ] Тест: in-memory `Client(mcp)`; monkeypatch `search.fetch_catalog` → `("ok", catalog)`
  и `search.build_http_client` → фейковый клиент; вызов `search_listings(url=...,
  include_keywords=[...])` возвращает `SearchResult` с отфильтрованными items.
  Второй тест: `kind != "ok"` → `ToolError`.
- [ ] Реализация: `register(mcp)` c `@mcp.tool async def search_listings(url, ctx,
  region=None, include_keywords=None, exclude_keywords=None, seller_blacklist=None,
  price_min=None, price_max=None, geo=None, max_age=None) -> SearchResult`.
  Тело: собрать `FilterSpec`; синхронную работу (build_http_client → fetch_catalog →
  extract_facts → apply_filters) выполнить в `asyncio.to_thread`; `kind != "ok"` →
  `ToolError`. `await ctx.info(...)` для прогресса.
- [ ] pytest + ruff + mypy зелёные. Commit: `feat(tools): search_listings`.

---

### Task 3: `check_proxy_health` тулза + регистрация

**Files:** Create `server/src/avito_mcp_server/tools/diagnostics.py`,
`server/tests/test_tools_diagnostics.py`; Modify `server.py`, `models.py` (+`ProxyHealth`)

- [ ] Тест: monkeypatch движок → пробный GET удаётся/блокируется; тулза возвращает
  `ProxyHealth(ok, cookie_provider, proxy_type, detail)`. Тест регистрации: сервер
  отдаёт `search_listings` и `check_proxy_health`.
- [ ] Реализация: модель `ProxyHealth`; `check_proxy_health` пробует получить
  каталог-URL через движок, сообщает конфиг + исход (в `asyncio.to_thread`).
  В `server.py`: `search.register(mcp)`, `diagnostics.register(mcp)`.
- [ ] pytest + ruff + mypy зелёные. Commit: `feat(tools): check_proxy_health + register`.

---

## Self-Review
- Покрытие: search_listings (§4 тулза 1, частично), check_proxy_health (§4 тулза 4),
  config/env (§7). get_listing/scan_new/export/notify/price_history — вне Фазы 2.
- Типы: `build_http_client()->HttpClient`, тулзы `-> SearchResult`/`ProxyHealth`.
- Async-граница: `asyncio.to_thread` вокруг синхронного curl_cffi-движка.
