# Phase 1 — Parsing Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Снести код официального API и построить движок парсинга каталога Avito
в `server/src/avito_mcp_server/` (модели, parser, cookies, proxies, http с
rotate-until-clean, filters) — по TDD, с моками сетевой границы.

**Architecture:** Толстое ядро без сети наружу в тестах. Провайдер кук (spfa) →
rotate-until-clean прокси → curl_cffi (`impersonate`) + follow SSR-редиректа →
`find_json_on_page` → факты. Каждый модуль изолирован за своим интерфейсом.
MCP-тулзы поверх движка — Фаза 2 (здесь их НЕ добавляем).

**Tech Stack:** Python ≥3.12, `curl_cffi`, `beautifulsoup4`, `pydantic` 2.13,
`requests` (spfa), pytest (`asyncio_mode=auto`), `httpx.MockTransport`/monkeypatch.

**Context7 (обязательно перед кодом):** сверься с Context7 по установленным версиям
(`curl_cffi`, `pydantic` 2.13, `bs4`) прежде чем писать реализацию. Код ниже
основан на валидированном живьём `robust_run.py`, но API мог измениться.

**Fixtures (уже в репо):** `server/tests/fixtures/redirect_stub.html` (реальная
страница с `<script type="mime/invalid" data-mfe-state="true">`, `loaderData.data`
= редирект-заглушка), `server/tests/fixtures/sample_listings.json` (50 фактов).

---

### Task 1: Снос официального API + движковые зависимости

**Files:**
- Modify: `server/pyproject.toml` (+`curl_cffi`, +`beautifulsoup4`)
- Modify: `server/src/avito_mcp_server/server.py` (убрать `ping`, `official_api`, `own_items`)
- Delete: `server/src/avito_mcp_server/official_api.py`, `tools/official_api.py`, `tools/own_items.py`
- Modify: `server/src/avito_mcp_server/models.py` (убрать `OwnItem`/`OwnItemsResult`/`AccountInfo`)
- Delete: `server/tests/test_official_api.py`, `test_tools_official_api.py`, `test_tools_own_items.py`
- Modify: `server/tests/test_server.py` (убрать ожидание офиц. тулз)

- [ ] **Step 1: Добавить зависимости движка**

В `server/pyproject.toml` секция `dependencies`:
```toml
dependencies = [
    "fastmcp>=3.0.0,<4",
    "httpx>=0.27",
    "curl_cffi>=0.7",
    "beautifulsoup4>=4.12",
]
```

- [ ] **Step 2: Установить**

Run: `cd server && uv sync --dev`
Expected: curl_cffi + beautifulsoup4 установлены, `uv.lock` обновлён.

- [ ] **Step 3: Удалить файлы официального API**

```bash
cd server
git rm src/avito_mcp_server/official_api.py src/avito_mcp_server/tools/official_api.py src/avito_mcp_server/tools/own_items.py
git rm tests/test_official_api.py tests/test_tools_official_api.py tests/test_tools_own_items.py
```

- [ ] **Step 4: Вычистить server.py**

Убрать из `server.py`: тулзу `ping` (+модель `Pong`, если только под неё), импорты
и вызовы `official_api.register(mcp)` / `own_items.register(mcp)`. Оставить инстанс
`mcp`, `register_skills(mcp)`, `main()`. Итог — сервер без тулз (Фаза 2 их добавит),
но со skills-раздачей.

- [ ] **Step 5: Вычистить models.py**

Удалить классы `OwnItem`, `OwnItemsResult`, `AccountInfo` и их импорты. Оставить
`Listing`, `SearchQuery`, `SearchResult` (в Task 2 их приведём к целевой форме).

- [ ] **Step 6: Обновить test_server.py**

Заменить тест на: сервер импортируется и содержит skills-ресурсы; НЕ ожидать
`ping`/`official_api_call`/`get_own_items`. Пример:
```python
from fastmcp import Client
from avito_mcp_server.server import mcp

async def test_server_instantiates_and_serves_skills():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert all(t.name not in {"ping", "official_api_call", "get_own_items",
                                  "get_account_info"} for t in tools)
        resources = await client.list_resources()
        assert any(str(r.uri).startswith("skill://") for r in resources)
```

- [ ] **Step 7: Тесты зелёные + линт**

Run: `cd server && uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: PASS (остались тесты skills_provider + новый test_server; официального API нет).

- [ ] **Step 8: Commit**

```bash
git add server/pyproject.toml server/uv.lock server/src/avito_mcp_server/ server/tests/
git commit -F <msg-file>
```
Сообщение: `feat(server): tear down official API, add engine deps`

---

### Task 2: `models.py` — Listing / SearchResult

**Files:**
- Modify: `server/src/avito_mcp_server/models.py`
- Test: `server/tests/test_models.py`

- [ ] **Step 1: Failing test**

```python
from avito_mcp_server.models import Listing, SearchResult

def test_listing_facts_only():
    it = Listing(id=1, title="1-к кв", price=6000000, url="https://avito.ru/x",
                 address="Нижний Новгород", params={"площадь": "36 м²"},
                 seller_id="brand", is_promotion=True, published_at=1700000000, views=42)
    assert it.id == 1 and it.price == 6000000 and it.views == 42
    assert not hasattr(it, "phone")  # ПДн не моделируем

def test_searchresult_count_computed():
    r = SearchResult(items=[Listing(id=1, title="a"), Listing(id=2, title="b")])
    assert r.count == 2
```

- [ ] **Step 2: Run — FAIL**

Run: `cd server && uv run pytest tests/test_models.py -q`
Expected: FAIL (нет полей/модели).

- [ ] **Step 3: Implement**

```python
class Listing(BaseModel):
    id: int
    title: str
    price: float | None = None
    url: str | None = None
    address: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    seller_id: str | None = None
    is_promotion: bool = False
    published_at: int | None = None
    views: int | None = None

class SearchResult(BaseModel):
    items: list[Listing]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.items)
```
Убрать поле `phone` полностью (ПДн не собираем). `SearchQuery` оставить как есть
или удалить, если не используется (проверь импорты).

- [ ] **Step 4: Run — PASS**

Run: `cd server && uv run pytest tests/test_models.py -q && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/src/avito_mcp_server/models.py server/tests/test_models.py
git commit -F <msg-file>
```
Сообщение: `feat(models): Listing/SearchResult (facts only)`

---

### Task 3: `parser.py` — find_json_on_page + классификация + extract_facts

**Files:**
- Create: `server/src/avito_mcp_server/parser.py`
- Test: `server/tests/test_parser.py`
- Create fixture: `server/tests/fixtures/catalog.html` (собрать в Step 1)

- [ ] **Step 1: Собрать catalog-фикстур**

`redirect_stub.html` содержит редирект, а не каталог. Создай минимальный
`server/tests/fixtures/catalog.html` — HTML с одним скриптом
`<script type="mime/invalid" data-mfe-state="true">` и html-escaped JSON вида:
```json
{"i18n":{"hasMessages":true},
 "loaderData":{"data":{"catalog":{"items":[
   {"id":7890298070,"title":"7-к. квартира, 306,5 м²","urlPath":"/nizhniy_novgorod/kvartiry/x_7890298070",
    "priceDetailed":{"value":98630444},"location":{"name":"Нижний Новгород"}},
   {"id":4269593793,"title":"2-к. квартира, 55,3 м²","urlPath":"/nizhniy_novgorod/kvartiry/y_4269593793",
    "priceDetailed":{"value":9826810},"location":{"name":"Нижний Новгород"}}
 ]}}}}
```
JSON внутри тега должен быть html-escaped (как отдаёт Avito: `&quot;` и т.п.) —
используй `html.escape` при генерации фикстура или запиши уже экранированным.

- [ ] **Step 2: Failing test**

```python
from pathlib import Path
from avito_mcp_server.parser import find_json_on_page, classify, extract_facts

FIX = Path(__file__).parent / "fixtures"

def test_find_json_catalog():
    html = (FIX / "catalog.html").read_text(encoding="utf-8")
    data = find_json_on_page(html)
    assert "catalog" in data and len(data["catalog"]["items"]) == 2

def test_classify_redirect():
    html = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    kind, payload = classify(html)
    assert kind == "redirect" and payload.startswith("/")

def test_classify_ok_and_extract():
    html = (FIX / "catalog.html").read_text(encoding="utf-8")
    kind, catalog = classify(html)
    assert kind == "ok"
    facts = extract_facts(catalog)
    assert facts[0].id == 7890298070 and facts[0].price == 98630444
    assert facts[0].address == "Нижний Новгород"
    assert facts[0].url == "https://www.avito.ru/nizhniy_novgorod/kvartiry/x_7890298070"
```

- [ ] **Step 3: Run — FAIL**

Run: `cd server && uv run pytest tests/test_parser.py -q`
Expected: FAIL (нет модуля).

- [ ] **Step 4: Implement** (порт из валидированного robust_run.py)

```python
import html as html_lib
import json
from bs4 import BeautifulSoup
from .models import Listing

def find_json_on_page(html_code: str) -> dict:
    soup = BeautifulSoup(html_code, "html.parser")
    for s in soup.select("script"):
        if (s.get("type") == "mime/invalid"
                and s.get("data-mfe-state") == "true"
                and "sandbox" not in s.text):
            try:
                data = json.loads(html_lib.unescape(s.text))
            except Exception:
                continue
            if data.get("i18n", {}).get("hasMessages"):
                return data.get("loaderData", {}).get("data", {})
    return {}

def classify(html_code: str):
    data = find_json_on_page(html_code)
    if not data:
        return "nojson", None
    if data.get("redirected") and data.get("url"):
        return "redirect", data["url"]
    catalog = data.get("catalog")
    if isinstance(catalog, dict) and catalog.get("items"):
        return "ok", catalog
    return "softblock", None

def extract_facts(catalog: dict) -> list[Listing]:
    out: list[Listing] = []
    for it in catalog.get("items", []):
        if not isinstance(it, dict) or not it.get("id"):
            continue
        pd = it.get("priceDetailed") or {}
        loc = it.get("location") or {}
        addr = it.get("addressDetailed") or {}
        geo = it.get("geo") or {}
        address = (addr.get("locationName")
                   or (loc.get("name") if isinstance(loc, dict) else None)
                   or (geo.get("formattedAddress") if isinstance(geo, dict) else None))
        up = it.get("urlPath")
        out.append(Listing(
            id=it["id"], title=it.get("title") or "",
            price=pd.get("value") if isinstance(pd, dict) else None,
            address=address,
            url=f"https://www.avito.ru{up}" if up else None,  # urlPath уже с ведущим /
            seller_id=str(it["sellerId"]) if it.get("sellerId") else None,
            is_promotion=bool(it.get("isPromotion")),
            published_at=it.get("sortTimeStamp"),
        ))
    return out
```
Примечание: URL склеивается БЕЗ лишнего `/` (`urlPath` уже начинается со `/`).

- [ ] **Step 5: Run — PASS**

Run: `cd server && uv run pytest tests/test_parser.py -q && uv run ruff check . && uv run mypy src`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server/src/avito_mcp_server/parser.py server/tests/test_parser.py server/tests/fixtures/catalog.html
git commit -F <msg-file>
```
Сообщение: `feat(parser): find_json_on_page + fact extraction`

---

### Task 4: `cookies/` — базовый интерфейс + spfa-провайдер

**Files:**
- Create: `server/src/avito_mcp_server/cookies/__init__.py`, `base.py`, `spfa.py`, `factory.py`
- Test: `server/tests/test_cookies.py`

- [ ] **Step 1: Failing test** (мок `requests.post` к spfa)

```python
import avito_mcp_server.cookies.spfa as spfa_mod
from avito_mcp_server.cookies.spfa import SpfaCookiesProvider

class _Resp:
    def __init__(self, code, payload): self.status_code = code; self._p = payload; self.ok = code < 400
    def json(self): return self._p
    def raise_for_status(self):
        if not self.ok: raise RuntimeError(self.status_code)

def test_spfa_buys_cookies(monkeypatch):
    calls = {}
    def fake_post(url, json, headers, timeout):
        calls["url"] = url
        return _Resp(200, {"results": {"id": "144514", "cookies": {"ft": "1"}}})
    monkeypatch.setattr(spfa_mod.requests, "post", fake_post)
    p = SpfaCookiesProvider(api_key="sk_test")
    cookies = p.get()
    assert cookies == {"ft": "1"} and p.last_id == "144514"
    assert calls["url"].endswith("/api/cookies/")
```

- [ ] **Step 2: Run — FAIL** → `cd server && uv run pytest tests/test_cookies.py -q`

- [ ] **Step 3: Implement** (упрощённый порт external_api.py)

`base.py`:
```python
from abc import ABC, abstractmethod

class CookiesProvider(ABC):
    @abstractmethod
    def get(self) -> dict: ...
    def update(self, response) -> None: ...
    @abstractmethod
    def handle_block(self) -> None: ...
```
`spfa.py`: класс `SpfaCookiesProvider(api_key)` с `API_URL="https://spfa.ru/api"`,
методами `get()` (возвращает `last_cookies` или `_buy()`), `_buy()` (`POST /api/cookies/`
`{"api_key"}` → `results.{id,cookies}`), `handle_block()` (`POST /api/unblock/`
`{"id","api_key"}`, при неудаче — `_buy()`). Использует `import requests`.
`factory.py`: `build_cookies_provider(provider: str, api_key, own_cookies)` →
`spfa`|`own`|`None`.

- [ ] **Step 4: Run — PASS** → `cd server && uv run pytest tests/test_cookies.py -q && uv run mypy src`

- [ ] **Step 5: Commit**
```bash
git add server/src/avito_mcp_server/cookies/ server/tests/test_cookies.py
git commit -F <msg-file>
```
Сообщение: `feat(cookies): spfa provider + interface`

---

### Task 5: `proxies/` — Mobile/Server/None + фабрика

**Files:**
- Create: `server/src/avito_mcp_server/proxies/__init__.py`, `proxy.py`, `factory.py`
- Test: `server/tests/test_proxies.py`

- [ ] **Step 1: Failing test**

```python
from avito_mcp_server.proxies.factory import build_proxy
from avito_mcp_server.proxies.proxy import MobileProxy, ServerProxy, NoProxy

def test_factory_mobile_when_change_url():
    p = build_proxy(proxy="u:p@h:1", change_url="https://chg?k=1")
    assert isinstance(p, MobileProxy) and p.httpx_proxy() == "http://u:p@h:1"

def test_factory_server_when_no_change_url():
    assert isinstance(build_proxy(proxy="u:p@h:1", change_url=""), ServerProxy)

def test_factory_none():
    assert isinstance(build_proxy(proxy="", change_url=""), NoProxy)

def test_mobile_rotate(monkeypatch):
    import avito_mcp_server.proxies.proxy as mod
    monkeypatch.setattr(mod.requests, "get",
        lambda url, params, timeout: type("R", (), {"status_code": 200, "json": lambda self: {"new_ip": "1.2.3.4"}})())
    assert MobileProxy("u:p@h:1", "https://chg?k=1").rotate() is True
```

- [ ] **Step 2: Run — FAIL** → `cd server && uv run pytest tests/test_proxies.py -q`

- [ ] **Step 3: Implement** (порт proxy.py + proxy_factory.py)

`proxy.py`: `Proxy` (ABC: `httpx_proxy()->str|None`, `rotate()->bool`),
`NoProxy`, `ServerProxy(url)` (`http://{url}`, `rotate`=noop→False),
`MobileProxy(url, change_url)` (`http://{url}`; `rotate()` → `requests.get(change_url+"&format=json")`,
200 → True). `factory.py`: `build_proxy(proxy, change_url)` — оба заданы → Mobile;
только proxy → Server; иначе None (совпадает с логикой §6 спеки).

- [ ] **Step 4: Run — PASS** → `cd server && uv run pytest tests/test_proxies.py -q && uv run mypy src`

- [ ] **Step 5: Commit**
```bash
git add server/src/avito_mcp_server/proxies/ server/tests/test_proxies.py
git commit -F <msg-file>
```
Сообщение: `feat(proxies): mobile/server/none + rotation`

---

### Task 6: `http/` — curl_cffi клиент с rotate-until-clean + follow-редирект

**Files:**
- Create: `server/src/avito_mcp_server/http/__init__.py`, `client.py`
- Test: `server/tests/test_http.py`

- [ ] **Step 1: Failing test** (мок сессии curl_cffi + прокси)

```python
import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient

class _Resp:
    def __init__(self, code, text=""): self.status_code = code; self.text = text

class _FakeSession:
    seq = []
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def request(self, *a, **k): return _Resp(*_FakeSession.seq.pop(0))
    headers = {}; proxies = {}

def test_rotate_until_clean(monkeypatch):
    # 403, 403, затем 200 — клиент ротирует и добивается успеха
    _FakeSession.seq = [(403,), (403,), (200, "<html>ok</html>")]
    monkeypatch.setattr(hc, "_build_session", lambda proxy: _FakeSession())
    rotations = {"n": 0}
    proxy = type("P", (), {"httpx_proxy": lambda self: "http://x", "rotate": lambda self: rotations.__setitem__("n", rotations["n"]+1) or True})()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=5, wait_after_rotate=0)
    resp = client.get("https://www.avito.ru/x")
    assert resp.status_code == 200 and rotations["n"] >= 1
```

- [ ] **Step 2: Run — FAIL** → `cd server && uv run pytest tests/test_http.py -q`

- [ ] **Step 3: Implement** (порт fetch() из robust_run.py)

`client.py`: модульная функция `_build_session(proxy_url)` (curl_cffi
`requests.Session(impersonate=random.choice(["chrome","edge","safari"]))`, UA,
`session.proxies`). Класс `HttpClient(proxy, cookies, max_attempts=18,
wait_after_rotate=9, block_codes=(401,403,429))` с методом `get(url) -> resp`:
цикл до `max_attempts`; на block-код → `proxy.rotate()` + пауза (`time.sleep`,
в тестах 0) + обновить куки; на 200 → вернуть; иначе ротация. `time.sleep`
вызывать через модульную обёртку, чтобы тесты мокали/обнуляли. Follow-редиректа —
на уровне вызывающего (Task Фазы 2 использует `classify`): здесь клиент только
возвращает 200-ответ; логику redirect→повторный get вынести в тонкий помощник
`fetch_catalog(client, url)` в этом же модуле (тест по фикстурам — Фаза 2).

- [ ] **Step 4: Run — PASS** → `cd server && uv run pytest tests/test_http.py -q && uv run mypy src`

- [ ] **Step 5: Commit**
```bash
git add server/src/avito_mcp_server/http/ server/tests/test_http.py
git commit -F <msg-file>
```
Сообщение: `feat(http): curl_cffi client with rotate-until-clean`

---

### Task 7: `filters/` — keyword/seller/price/geo/max_age

**Files:**
- Create: `server/src/avito_mcp_server/filters/__init__.py`, `filters.py`
- Test: `server/tests/test_filters.py`

- [ ] **Step 1: Failing test**

```python
from avito_mcp_server.models import Listing
from avito_mcp_server.filters.filters import apply_filters, FilterSpec

def _l(id, title, price, seller="s"):
    return Listing(id=id, title=title, price=price, seller_id=seller)

def test_price_and_keyword_filters():
    items = [_l(1, "1-к квартира", 5_000_000), _l(2, "гараж", 900_000),
             _l(3, "2-к квартира студия", 12_000_000)]
    spec = FilterSpec(include_keywords=["квартира"], exclude_keywords=["студия"],
                      price_min=1_000_000, price_max=10_000_000)
    out = apply_filters(items, spec)
    assert [i.id for i in out] == [1]

def test_seller_blacklist():
    items = [_l(1, "a", 1, seller="bad"), _l(2, "b", 1, seller="ok")]
    out = apply_filters(items, FilterSpec(seller_blacklist=["bad"]))
    assert [i.id for i in out] == [2]
```

- [ ] **Step 2: Run — FAIL** → `cd server && uv run pytest tests/test_filters.py -q`

- [ ] **Step 3: Implement**

`filters.py`: dataclass/BaseModel `FilterSpec` (include_keywords, exclude_keywords,
seller_blacklist, price_min, price_max, geo, max_age — все опциональны). Функция
`apply_filters(items: list[Listing], spec) -> list[Listing]`: последовательные
предикаты (регистронезависимый keyword по title; seller_id not in blacklist;
price в [min,max]; published_at по max_age от «сейчас» — время передавать
параметром/`time.time()` через обёртку для тестируемости).

- [ ] **Step 4: Run — PASS** → `cd server && uv run pytest tests/test_filters.py -q && uv run ruff check . && uv run mypy src`

- [ ] **Step 5: Commit**
```bash
git add server/src/avito_mcp_server/filters/ server/tests/test_filters.py
git commit -F <msg-file>
```
Сообщение: `feat(filters): keyword/seller/price/geo/max_age`

---

## Self-Review (при написании плана)

- **Покрытие §11 Фаза 1 спеки:** модели → Task 2; parser (find_json) → Task 3;
  http (rotate-until-clean) → Task 6; proxies → Task 5; cookies (spfa) → Task 4;
  filters → Task 7; снос офиц. API + деп → Task 1.
- **Плейсхолдеры:** нет — код в каждом Step. Фикстур `catalog.html` собирается в
  Task 3 Step 1 из документированной структуры.
- **Консистентность типов:** `Listing`/`SearchResult` (Task 2) используются в
  `extract_facts` (Task 3) и `apply_filters` (Task 7); `CookiesProvider` (Task 4)
  и `Proxy` (Task 5) инъектируются в `HttpClient` (Task 6). Имена согласованы.
- **Вне Фазы 1 (Фаза 2):** MCP-тулзы, пагинация `web/1/js/items`, storage/sqlite,
  export, notifications, `get_price_history` — здесь НЕ реализуются.
