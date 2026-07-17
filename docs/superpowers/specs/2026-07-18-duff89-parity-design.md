# Дизайн: фичепаритет с Duff89/parser_avito в MCP-плагине

**Дата:** 2026-07-18
**Статус:** одобрен пользователем, готов к плану реализации
**Ветка:** `feat/duff89-parity`

## 1. Цель и контекст

Превратить `avito-mcp-plugin` в полнофункциональный Avito-тулкит для AI-агентов
с **фичепаритетом** [Duff89/parser_avito](https://github.com/Duff89/parser_avito),
поставляемый как **MCP-тулзы + skills** (без GUI). Текущая официально-API-центричная
реализация («Линия A») удаляется целиком; сервер строится как порт ядра Duff89,
обёрнутый в MCP.

Метод Duff89 воспроизведён и **валидирован живьём** 2026-07-18: spfa-куки → ротация
IP до чистого → curl_cffi (`impersonate`) + follow SSR-редиректа → извлечение
`loaderData.data.catalog` → 50 объявлений (НН/квартиры). Артефакты: `robust_run.py`,
`page.html`, `result/listings.json` (станут фикстурами).

### Ключевые решения (согласованы)

1. **Legal-позиция:** guardrails-документация убирается. Паритет с Duff89 по
   фактическим данным и мониторингу; правовой риск оператора — на пользователе.
   **Исключение (этическая граница):** `parse_phone` — сбор телефонов продавцов
   (ПДн третьих лиц в промышленном масштабе) — намеренно **НЕ реализуется**.
2. **Архитектура:** agent-driven stateless-тулзы + лёгкое sqlite-состояние.
   Мониторинг — через внешний планировщик (агент/cron/`/schedule`), не фоновый цикл
   в сервере.
3. **Разворот к Duff89:** удалить все существующие тулзы (официальный API + `ping`);
   внутренняя структура сервера зеркалит модули Duff89.

## 2. Область изменений

### Удаляется полностью

| Категория | Артефакты |
|---|---|
| Тулзы | `ping`, `get_own_items`, `get_account_info`, `official_api_call` |
| Инфраструктура офиц. API | `official_api.py` (OAuth2-клиент + allowlist `validate_endpoint`), `tools/official_api.py`, `tools/own_items.py` |
| Модели | `OwnItem`, `OwnItemsResult`, `AccountInfo` |
| Скилы | `avito-legal-guardrails`, `avito-official-api` |
| Доки | `docs/avito-legal.md` |
| Env | `AVITO_CLIENT_ID`, `AVITO_CLIENT_SECRET` |
| Тесты | все тесты официального API и guardrails |

> **Компромисс (зафиксирован):** вместе с официальным API уходит управление своим
> кабинетом — легальнейшая и рабочая часть. В Duff89 её нет → удаляем осознанно.

### GUI (flet) — не портируется

Неприменим к плагину: **агент и есть UI**. Фиксируется в доках как осознанное
исключение.

## 3. Целевая архитектура

Принцип прежний — «толстое ядро (MCP) + тонкие адаптеры + skills» — но ядро теперь
несёт весь движок Duff89. Внутренняя структура `server/src/avito_mcp_server/`
зеркалит модульную раскладку Duff89:

```text
avito_mcp_server/
├── cookies/       # провайдеры кук: spfa (external_api), own, playwright
│                  #   ← parser/cookies/{external_api,own_cookies}.py + get_cookies.py
├── proxies/       # Mobile/Server/None + ротация-до-чистого ← parser/proxies/
├── http/          # curl_cffi клиент (impersonate, retry) ← parser/http/client.py
├── export/        # xlsx / json / csv ← parser/export/
├── notifications/ # Telegram, VK ← integrations/notifications/
├── filters/       # keyword/seller/price/geo/max_age ← filters/ads_filter.py
├── storage/       # sqlite: dedup + история цены ← db_service.py
├── models.py      # Listing/SearchResult ← models.py Duff89 (факты + опции)
├── parser.py      # ядро: find_json_on_page + пагинация web/1/js/items
├── skills_provider.py  # (остаётся) раздача skills по MCP
├── tools/         # тонкий MCP-слой поверх ядра (register(mcp) на группу)
└── server.py      # инстанс + main() + регистрация групп тулз
```

### Улучшение над Duff89 (валидировано живьём)

HTTP-клиент сохраняет подход Duff89 (curl_cffi + `impersonate`), но **заменяет
retry-логику**: вместо одной ротации IP — **rotate-until-clean** (до
`AVITO_MAX_ROTATE_ATTEMPTS`, дефолт 18) + follow SSR-редиректа на канонический URL.
Это чинит найденный дефект Duff89 (`block_threshold`+`max_count_of_retry` дают одну
ротацию и сдачу), из-за которого штатный парсер не пробивал смешанный IP-пул.

## 4. Инвентарь MCP-тулз (7 шт., все — фичи Duff89)

Фильтры и `parse_views` — **параметры**, не отдельные тулзы. Держит нас глубоко под
лимитом Anthropic «< 20 тулз». `parse_phone` из Duff89 **исключён** (ПДн третьих лиц).

| # | Тулза | Duff89-источник | Ключевые параметры |
|---|---|---|---|
| 1 | `search_listings` | `AvitoParse.parse()` | `url_or_query`, `region`, `pages`, `include_keywords`, `exclude_keywords`, `seller_blacklist`, `price_min/max`, `geo`, `max_age`, `parse_views` |
| 2 | `get_listing` | детали объявления | `id_or_url`, `with_views` |
| 3 | `scan_new_listings` | dedup + смена цены (мониторинг-примитив) | фильтры + пишет в sqlite; возвращает только новое/подешевевшее |
| 4 | `check_proxy_health` | ротация/диагностика прокси | — |
| 5 | `send_notification` | Telegram/VK | `channel` (telegram\|vk), `message`, `targets?` |
| 6 | `export_listings` | xlsx/json/csv | `items`, `format`, `path?` |
| 7 | `get_price_history` | история цены | `listing_id` |

Возврат — Pydantic-модели (structured output). Ошибки наружу — через `ToolError`.

## 5. Хранилище (sqlite)

Путь через `AVITO_DB_PATH`. Ленивое создание, без серверного lifespan.

- `seen_items(id PK, url, title, price, first_seen, last_seen)` — dedup.
- `price_history(item_id, price, seen_at)` — история цены.

Питает `scan_new_listings` (сравнение с прошлым проходом) и `get_price_history`.

## 6. Провайдеры

### Куки (`AVITO_COOKIE_PROVIDER`, дефолт `spfa`)

- `spfa` — `POST spfa.ru/api/cookies` + `/unblock` (валидировано). Ключ `SPFA_API_KEY`.
- `own` — куки пользователя (`AVITO_OWN_COOKIES`).
- `playwright` — браузерная добыча (куки `ft`), опционально, тяжёлая extra-зависимость.

Единый интерфейс `CookiesProvider.get()/update()/handle_block()`.

### Прокси (`AVITO_PROXY` + опц. `AVITO_PROXY_CHANGE_URL`)

- `MobileProxy` (есть change-url → ротация) / `ServerProxy` (статик) / `NoProxy`.
- Формат `user:pass@host:port`.

### HTTP (curl_cffi)

`impersonate` ∈ {chrome, edge, safari}, случайный UA, прокси, rotate-until-clean,
follow-редирект, `find_json_on_page` (`script[type=mime/invalid][data-mfe-state=true]`
→ `loaderData.data.catalog.items`).

## 7. Переменные окружения

| Переменная | Назначение |
|---|---|
| `SPFA_API_KEY` | ключ spfa (провайдер кук) |
| `AVITO_COOKIE_PROVIDER` | `spfa`\|`own`\|`playwright` (дефолт `spfa`) |
| `AVITO_OWN_COOKIES` | куки для провайдера `own` |
| `AVITO_PROXY` | `user:pass@host:port` |
| `AVITO_PROXY_CHANGE_URL` | URL ротации IP (→ MobileProxy) |
| `AVITO_TG_TOKEN`, `AVITO_TG_CHAT_IDS` | Telegram-уведомления |
| `AVITO_VK_TOKEN`, `AVITO_VK_USER_IDS` | VK-уведомления |
| `AVITO_DB_PATH` | путь sqlite |
| `AVITO_MAX_ROTATE_ATTEMPTS` | лимит ротаций (дефолт 18) |
| `AVITO_SKILLS_DIR`, `CLAUDE_PLUGIN_ROOT` | (остаются) резолв skills |

Удаляются: `AVITO_CLIENT_ID`, `AVITO_CLIENT_SECRET`.

## 8. Модели данных

Порт `models.py` Duff89, упрощённый до фактов + опций:

```python
class Listing(BaseModel):
    id: int
    title: str
    price: float | None
    url: str | None
    address: str | None
    params: dict[str, str]        # площадь, этажность из title/характеристик
    seller_id: str | None
    is_promotion: bool = False
    published_at: int | None       # sortTimeStamp
    views: int | None = None       # если parse_views

class SearchResult(BaseModel):
    items: list[Listing]
    count: int                     # computed
```

## 9. Переписывание документации

**Удаляются:** `docs/avito-legal.md`, скилы `avito-legal-guardrails`,
`avito-official-api`.

**Переписываются под новый фичесет:** `CLAUDE.md`, `README.md`,
`docs/architecture.md`, `docs/mcp-server.md`, `docs/roadmap.md`, `docs/skills.md`,
`docs/portability.md`, `docs/avito-scraping.md`, `.env.example`, `AGENTS.md`,
`GEMINI.md`, манифесты (`plugin.json`, `marketplace.json`, `.mcp.json`,
`gemini-extension.json`, `.cursor-plugin/plugin.json`).

**Скилы:**
- `scraping-avito` → полное how-to движка (spfa + rotate-until-clean + redirect +
  extract), без legal-обрамления.
- `using-avito-mcp` → новый список из 7 тулз.
- (опц., решить в плане) новые `avito-monitoring`, `avito-notifications`.

## 10. Тестирование (TDD)

- Порт по модулям с моками сетевой границы: `curl_cffi`/`requests` через
  подменяемый транспорт; HTML-фикстуры из живого `page.html`.
- `result/listings.json` → эталон извлечения фактов.
- In-memory `Client(mcp)` для тулз (structured output).
- Каждый модуль (cookies/proxies/http/parser/filters/storage/export/notifications)
  — RED→GREEN→REFACTOR.

## 11. Порядок реализации

- **Фаза 0 — документация** (по запросу «сначала доки»): переписать все доки/скилы/
  манифесты под целевой дизайн. Тулзы помечаются статусом «план», как сейчас.
- **Фаза 1 — движок:** модели, parser (find_json), http (rotate-until-clean),
  proxies, cookies (spfa), filters.
- **Фаза 2 — тулзы парсинга:** `search_listings`, `get_listing`, `check_proxy_health`.
- **Фаза 3 — состояние/мониторинг:** storage (sqlite), `scan_new_listings`,
  `get_price_history`.
- **Фаза 4 — сайд-эффекты:** `export_listings`, `send_notification`.
- **Фаза 5 — доп. провайдеры кук:** `own`, `playwright` (extra).

Каждая фаза — отдельный цикл spec→plan→implement при необходимости; данная спека —
зонтичная.

## 12. Открытые вопросы (решить в плане)

- Нужны ли отдельные скилы `avito-monitoring` / `avito-notifications` или достаточно
  расширить `using-avito-mcp`.
- Дефолтный путь `AVITO_DB_PATH` (рабочий каталог vs data-dir).
- Публиковать ли `playwright`-провайдер как основной extra или отдельный пакет.
