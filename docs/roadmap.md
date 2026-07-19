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

- [x] `models.py` — `Listing`/`SearchResult`, упрощённые до фактов + опций
- [x] `parser.py` — ядро: `find_json_on_page`
      (`script[type=mime/invalid][data-mfe-state=true]` →
      `loaderData.data.catalog.items`) + пагинация `web/1/js/items`
- [x] `http/` — curl_cffi клиент (`impersonate` ∈ {chrome, edge, safari},
      случайный UA) с **rotate-until-clean** (наше улучшение retry-логики: до
      `AVITO_MAX_ROTATE_ATTEMPTS`, дефолт 18, вместо одной ротации —
      типичный дефект наивной retry-логики: одна ротация → сдача) + follow
      SSR-редиректа на канонический URL категории
- [x] `proxies/` — `MobileProxy` (с change-url) / `ServerProxy` (статик) /
      `NoProxy`
- [x] `cookies/` — провайдер `spfa` (`POST spfa.ru/api/cookies` + `/unblock`,
      `SPFA_API_KEY`), единый интерфейс `CookiesProvider.get()/update()/handle_block()`
- [x] `filters/` — keyword/seller/price/geo/max_age

## Фаза 2 — тулзы парсинга

- [x] `search_listings` — разовый поиск каталога
- [x] `get_listing` — детали объявления
- [x] `check_proxy_health` — диагностика прокси/ротации

## Фаза 3 — состояние/мониторинг

- [x] `storage/` — Postgres проекта Supabase (`AVITO_SUPABASE_DSN`), SQLAlchemy ORM:
      `seen_items` (dedup) + `price_history` + `proxy_cooldown`
- [x] `scan_new_listings` — dedup + отслеживание цены (мониторинг-примитив;
      мониторинг снаружи — через внешний планировщик/`/schedule`, не фоновый
      цикл в сервере)
- [x] `get_price_history` — история цены из Postgres

## Фаза 4 — сайд-эффекты

- [x] `export_listings` — xlsx/json/csv
- [x] `send_notification` — Telegram/VK (`AVITO_TG_TOKEN`/`AVITO_TG_CHAT_IDS`,
      `AVITO_VK_TOKEN`/`AVITO_VK_USER_IDS`)

## Фаза 5 — доп. провайдеры кук

- [x] Провайдер `own` (`AVITO_OWN_COOKIES`) — куки пользователя
- [x] Провайдер `playwright` (браузерная добыча куки `ft`) — опционально,
      тяжёлая extra-зависимость (``pip install avito-mcp-server[playwright]``)

## Фаза 6 — глубина выдачи и диагностика

- [x] Пагинация каталога: `pages` в `search_listings` и `scan_new_listings`,
      обход по `catalog.pager.next` с дедупом по id (внутренний API
      `web/1/js/items` не понадобился — ссылки на страницы есть в самом каталоге)
- [x] `AVITO_PAGE_PAUSE` (дефолт 1.0 с) — пауза между страницами, иначе обход
      выжигает IP быстрее, чем собирает данные
- [x] Адрес из `geo.formattedAddress` + `geo.geoReferences` (улица, метро, район)
      вместо города — без этого `geo`-фильтр не мог сработать в принципе
- [x] Статус `firewall` в `classify` + `explain_status`: тулзы называют причину
      блокировки и следующий шаг (`AVITO_PROXY`), а не отдают сырой код
- [x] Логирование попыток HTTP и обхода страниц (`logging`) — долгие прогоны
      наблюдаемы вживую

## Фаза 7 — автоматизация прокси и кук

- [x] `ProxyPool` — `AVITO_PROXY` принимает список через запятую; при блокировке
      перебираются адреса, круг замкнулся → `rotate()` возвращает `False`
- [x] Файловый кэш кук spfa (`AVITO_COOKIES_CACHE`, дефолт
      `~/.cache/avito-mcp-server/cookies.json`, TTL 12 ч): каждый вызов тулзы —
      новый процесс, без кэша куки покупались заново (~12 ₽ за штуку).
      Проверено живьём: два экземпляра, одна покупка
- [x] Кэш инвалидируется при неудачном `unblock` — мёртвые куки не переживают
      блокировку

- [x] Экспоненциальный backoff между ротациями (потолок 60 с) вместо фиксированных
      9 с; после последней попытки не спим — всё равно сдаёмся
- [x] Память о выжженных IP в Postgres (`proxy_cooldown`, TTL 30 мин): пул стартует
      с адреса вне cooldown и помечает текущий при блокировке. Включается сама,
      если задан `AVITO_SUPABASE_DSN`; без БД пул работает без памяти
- [x] `check_proxy_health` проверяет **каждый** адрес пула и возвращает `probes`
      (какой живой, какой нет). Учётные данные маскируются — наружу только host:port
- [x] `AVITO_PROXY_LIST_URL` — список портов подхватывается из кабинета
      (JSON-массив или текст по строке); кабинет недоступен → фоллбэк на `AVITO_PROXY`

Не автоматизируется намеренно: покупка прокси/пополнение баланса (финансовые
операции) и ввод учётных данных в кабинеты провайдеров — это делает человек,
плагин получает готовые значения через env.

## Фаза 8 — Postgres (Supabase) как единственное хранилище

- [x] Проект Supabase `avito-mcp-plugin` (ref `wvszgigxihuaaardchft`, eu-central-1),
      миграция `supabase/migrations/20260719_avito_storage.sql`
- [x] Схема `avito` (не `public`), таблицы `seen_items` / `price_history` /
      `proxy_cooldown`; `timestamptz` вместо epoch-float, `numeric` вместо `real`
      для цен, `generated always as identity` вместо автоинкремента
- [x] RLS включён на всех таблицах, политик нет намеренно: доступ только у
      `service_role`; `anon`/`authenticated` отозваны со схемы. `get_advisors`
      показывает лишь INFO `rls_enabled_no_policy` — это и есть замысел
- [x] `storage/supabase.py` — SQLAlchemy ORM; наружу epoch-float, иначе поедут
      модели тулз
- [x] sqlite удалён целиком (код, тесты, документация): один бэкенд — один путь.
      Хранилище настраивается единственной переменной `AVITO_SUPABASE_DSN`
- [x] ORM-модели `storage/models.py` (SQLAlchemy 2.0: `DeclarativeBase`,
      `Mapped`/`mapped_column`, схема через `__table_args__`), upsert — диалектный
      `postgresql.insert(...).on_conflict_do_update()`
- [x] `sqlalchemy` и `psycopg[binary]` — основные зависимости: хранилище
      обязательное, прятать его в extra больше незачем
- [x] Тесты хранилища идут против **настоящего** Postgres (skip без DSN); подменять
      его другой СУБД нельзя — диалектный upsert и `timestamptz` там ведут себя
      иначе. Тулзы тестируются на `FakeStorage` (`tests/fakes.py`)

Схема `avito` закрыта от Data API, поэтому доступ идёт прямым подключением по
DSN, а не через REST/PostgREST.

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
