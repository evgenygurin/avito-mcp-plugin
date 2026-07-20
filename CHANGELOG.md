# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [семантическому версионированию](https://semver.org/lang/ru/).

## [Unreleased]

## [0.2.1] — 2026-07-20

### Fixed

- `check_proxy_health` для одиночного прокси (не пула) гонял полный
  rotate-until-clean — до 18 попыток с экспоненциальным backoff (до ~20 минут),
  и `timeout=180` тулзы это не останавливал: работа уходит в
  `asyncio.to_thread`, а обычный поток нельзя прервать, поэтому по истечении
  таймаута клиент получал ошибку, а поток продолжал висеть в фоне. Теперь
  диагностика одиночного прокси, как и пула, использует короткий пробный
  клиент (3 попытки).

## [0.2.0] — 2026-07-20

### Fixed (устойчивость сетевого слоя)

- Тулзы больше не висят по четверти часа на блокировке IP. `HttpClient.get`
  выбирал весь бюджет попыток даже когда `Proxy.rotate()` возвращал `False` —
  то есть менять выходной адрес было не на что — и досыпал 903 с backoff по
  одному и тому же 403. Теперь цикл обрывается сразу; транспортные ошибки
  (таймаут, обрыв TCP) по-прежнему повторяются, потому что лечатся повтором,
  а не сменой IP.
- `get_listing` следует SSR-редиректу на канонический URL. Раньше тулза била
  `client.get` напрямую и на странице-редиректе отвечала «не удалось извлечь
  данные объявления».
- `AVITO_MAX_ROTATE_ATTEMPTS=0` даёт контрактную ошибку вместо
  `UnboundLocalError`.

### Changed (устойчивость сетевого слоя)

- Дефолт `AVITO_MAX_ROTATE_ATTEMPTS` — 5 вместо 18. Худший случай ожидания:
  903 с → 123 с. Чистый IP, не найденный за пять ротаций, не найдётся и за
  восемнадцать.
- Обход SSR-редиректов вынесен в `_follow()`; `fetch_catalog` стал обёрткой
  над ним, добавлена `fetch_page()` для страниц объявлений.

### Changed (разворот к полнофункциональному парсингу каталога Avito)

- Проект переориентирован с официального API `api.avito.ru` на полнофункциональный
  парсер публичного каталога: движок парсинга (провайдеры кук, ротация прокси до
  чистого IP, curl_cffi, извлечение JSON со страницы) вместо OAuth2-клиента над
  официальным API.
- См. [`docs/superpowers/specs/2026-07-18-avito-parser-design.md`](docs/superpowers/specs/2026-07-18-avito-parser-design.md)
  — целевой дизайн 7 MCP-тулз (`search_listings`, `get_listing`,
  `scan_new_listings`, `check_proxy_health`, `send_notification`,
  `export_listings`, `get_price_history`).

### Removed (разворот к полнофункциональному парсингу каталога Avito)

- Тулзы официального API: `ping`, `official_api_call`, `get_own_items`,
  `get_account_info`.
- Клиент официального API (`official_api.py`, OAuth2 `client_credentials` +
  allowlist `validate_endpoint`) и модели `OwnItem`, `OwnItemsResult`, `AccountInfo`.
- Переменные окружения `AVITO_CLIENT_ID`, `AVITO_CLIENT_SECRET`.
- Скилы `avito-legal-guardrails` и `avito-official-api`, документ
  `docs/avito-legal.md`.
- Правовые guardrails как документационный слой: полнофункциональный фичесет
  парсинга строится по фактическим данным и мониторингу, правовой риск — на
  операторе. Единственное
  сохранённое ограничение — `parse_phone` (сбор телефонов продавцов) намеренно
  **не реализуется** ни в одной тулзе.

### Added (Этап 5 — релиз-подготовка)

- `LICENSE` (MIT), `.env.example` (переменные окружения сервера).
- `scripts/check_versions.py` — проверка синхронности версий в 5 манифестах.
- `docs/releasing.md` — процесс релиза и публикации в PyPI.

### Added (Этап 4 — переносимость)

- Раздача `skills/` по MCP через `SkillsProvider` (`skill://<name>/SKILL.md`);
  модуль `skills_provider.py` с graceful-резолвом пути (`AVITO_SKILLS_DIR` →
  `${CLAUDE_PLUGIN_ROOT}/skills` → каталог репозитория).
- Готовые конфиги MCP-сервера для Cursor/Codex/Gemini/VS Code в
  `examples/mcp-configs/`.
- Тонкие адаптеры: `.cursor-plugin/plugin.json`, `.codex/INSTALL.md`.
- `gemini-extension.json` теперь включает блок `mcpServers` — установка
  Gemini-расширения поднимает MCP-сервер `avito` в один шаг.

### Changed

- Финализированы все скилы, актуальные на тот момент (Этап 2) по методологии
  `writing-skills`: убран статус «черновик», описания приведены к формату
  WHEN-триггеров, добавлен discipline-блок про капчу (`scraping-avito`).
  Wiki-ссылки `[[…]]` заменены на markdown-ссылки. (Два из четырёх тогдашних
  скилов позже удалены при развороте к полнофункциональному парсингу каталога
  Avito — см. «Removed» выше.)
- RED-baseline и verify проведены на субагентах.

### Added

- Доменные Pydantic-модели: `Listing`, `SearchQuery`, `SearchResult`.
- Утилита `extract_listing_id` (id объявления из URL или «голого» id).
- Тестовый слой: 26 тестов через in-memory `Client(mcp)` и `httpx.MockTransport`;
  ruff + mypy чисты.
- Зависимость `httpx`.
- (Клиент официального API и тулза `official_api_call`, добавленные на этом
  этапе, позже удалены при развороте к полнофункциональному парсингу каталога
  Avito — см. «Removed» выше.)

## [0.1.0] — 2026-07-17

Первичный каркас и документация проекта.

### Added

- Каркас плагина: `.claude-plugin/plugin.json`, `marketplace.json`, `.mcp.json`,
  `gemini-extension.json`.
- 4 skeleton-скила: `using-avito-mcp`, `scraping-avito`, `avito-legal-guardrails`,
  `avito-official-api`.
- Заготовка MCP-сервера `avito-mcp-server` (FastMCP v3, src-layout, тулза `ping`).
- Документация в `docs/`: архитектура, skills, MCP-сервер, парсинг Avito,
  правовые аспекты, переносимость, roadmap.
- Корневые файлы: `README.md`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`,
  `CONTRIBUTING.md`.
- Исследовательские материалы в `docs/researches/`.

### Notes

- Skills и тулзы MCP-сервера — заготовки; рабочая логика в разработке (см.
  [`docs/roadmap.md`](docs/roadmap.md)).

[Unreleased]: https://github.com/evgenygurin/avito-mcp-plugin/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/evgenygurin/avito-mcp-plugin/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/evgenygurin/avito-mcp-plugin/releases/tag/v0.1.0
