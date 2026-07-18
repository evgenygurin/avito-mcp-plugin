# Roadmap

Проект разворачивается в полнофункциональный парсер публичного каталога Avito.
Полный дизайн, обоснование решений и инвентарь тулз —
[спека парсера](superpowers/specs/2026-07-18-avito-parser-design.md).
Фазы 0–5 ниже — актуальный план реализации (§11 спеки).

## Линия A — официальный API (удалена)

Прежняя реализация — тулзы `ping`, `official_api_call`, `get_own_items`,
`get_account_info` поверх OAuth2-клиента официального API (`official_api.py` +
allowlist `validate_endpoint`), модели `OwnItem`/`OwnItemsResult`/`AccountInfo`,
скилы `avito-legal-guardrails`/`avito-official-api`, `docs/avito-legal.md` —
**удаляется целиком** в пользу целевого фичесета парсера (см. спеку, §2
«Удаляется полностью»).

> **Компромисс (зафиксирован в спеке):** вместе с официальным API уходит
> управление своим кабинетом — легальнейшая и рабочая часть текущей реализации.
> В целевом дизайне парсера её нет → удаляем осознанно, ради полного
> фичесета парсинга.

## Фаза 0 — документация

По запросу «сначала доки»: переписать всё под целевой дизайн ещё до кода движка.
Тулзы на этом этапе помечаются статусом **«🔜 план»** — код ещё не написан.

- [x] Переписать `CLAUDE.md`, `README.md`, `docs/architecture.md`,
      `docs/mcp-server.md`, `docs/roadmap.md`, `docs/skills.md`,
      `docs/portability.md`, `docs/avito-scraping.md`, `.env.example`,
      `AGENTS.md`, `GEMINI.md`
- [x] Обновить манифесты: `plugin.json`, `marketplace.json`, `.mcp.json`,
      `gemini-extension.json`, `.cursor-plugin/plugin.json`
- [x] Удалить `docs/avito-legal.md` и скилы `avito-legal-guardrails`,
      `avito-official-api`
- [x] Скил `scraping-avito` → полное how-to движка (spfa + rotate-until-clean +
      redirect + extract), без legal-обрамления
- [x] Скил `using-avito-mcp` → список из 7 новых тулз

## Фаза 1 — движок

Движок парсинга в `server/src/avito_mcp_server/` (модульная раскладка —
см. §3 спеки).

- [ ] `models.py` — `Listing`/`SearchResult`, упрощённые до фактов + опций
- [ ] `parser.py` — ядро: `find_json_on_page`
      (`script[type=mime/invalid][data-mfe-state=true]` →
      `loaderData.data.catalog.items`) + пагинация `web/1/js/items`
- [ ] `http/` — curl_cffi клиент (`impersonate` ∈ {chrome, edge, safari},
      случайный UA) с **rotate-until-clean** (наше улучшение retry-логики: до
      `AVITO_MAX_ROTATE_ATTEMPTS`, дефолт 18, вместо одной ротации —
      типичный дефект наивной retry-логики: одна ротация → сдача) + follow
      SSR-редиректа на канонический URL категории
- [ ] `proxies/` — `MobileProxy` (с change-url) / `ServerProxy` (статик) /
      `NoProxy`
- [ ] `cookies/` — провайдер `spfa` (`POST spfa.ru/api/cookies` + `/unblock`,
      `SPFA_API_KEY`), единый интерфейс `CookiesProvider.get()/update()/handle_block()`
- [ ] `filters/` — keyword/seller/price/geo/max_age

## Фаза 2 — тулзы парсинга

- [ ] `search_listings` — разовый поиск каталога
- [ ] `get_listing` — детали объявления
- [ ] `check_proxy_health` — диагностика прокси/ротации

## Фаза 3 — состояние/мониторинг

- [ ] `storage/` — sqlite (`AVITO_DB_PATH`, ленивое создание): `seen_items`
      (dedup) + `price_history`
- [ ] `scan_new_listings` — dedup + отслеживание цены (мониторинг-примитив;
      мониторинг снаружи — через внешний планировщик/`/schedule`, не фоновый
      цикл в сервере)
- [ ] `get_price_history` — история цены из sqlite

## Фаза 4 — сайд-эффекты

- [ ] `export_listings` — xlsx/json/csv
- [ ] `send_notification` — Telegram/VK (`AVITO_TG_TOKEN`/`AVITO_TG_CHAT_IDS`,
      `AVITO_VK_TOKEN`/`AVITO_VK_USER_IDS`)

## Фаза 5 — доп. провайдеры кук

- [ ] Провайдер `own` (`AVITO_OWN_COOKIES`) — куки пользователя
- [ ] Провайдер `playwright` (браузерная добыча куки `ft`) — опционально,
      тяжёлая extra-зависимость; решить, публиковать как основной extra или
      отдельный пакет

Каждая фаза — отдельный цикл spec→plan→implement при необходимости; спека
парсера — зонтичная.

## Исключено из фич

`parse_phone` (сбор телефонов продавцов) — намеренно **не
реализуется**: ПДн третьих лиц в промышленном масштабе. Не появляется ни как
тулза, ни как параметр, ни в моделях.

## Триггеры смены решений

- Тулз > 20–25 → точность выбора тулзы падает; разбить на focused-серверы.
- Нужен remote/мультиюзер → streamable HTTP + JWT + Docker + reverse proxy (TLS).
- Codex как таргет + HTTP → нужен `mcp-proxy`.
- Нужны build-hooks/VCS-версии → сменить `uv_build` на `hatchling`.
