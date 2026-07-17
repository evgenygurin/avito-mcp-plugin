# Roadmap

План развития от текущей заготовки к production-плагину. Этапы взяты из раздела
Recommendations
[исследования по архитектуре](researches/compass_artifact_wf-3195fb5c-c4d3-546f-886e-b0cbcbdf6c62_text_markdown.md).

## Текущее состояние (v0.1.0)

- [x] Репозиторий, документация, каркас плагина
- [x] Манифесты: `plugin.json`, `marketplace.json`, `.mcp.json`, `gemini-extension.json`
- [x] 4 skeleton-скила (`using-avito-mcp`, `scraping-avito`, `avito-legal-guardrails`, `avito-official-api`)
- [x] MCP-сервер (`server/`): тулзы `ping` и `official_api_call`, модели, утилиты, 26 тестов
- [ ] Парсинг-тулзы, финализация skills, CI, публикация — ниже

## Этап 1 — MCP-сервер

- [x] `uv sync --dev`, зафиксирован `uv.lock`, добавлен `httpx`
- [x] Доменные Pydantic-модели (`Listing`, `SearchQuery`, `SearchResult`)
- [x] Утилиты (`extract_listing_id`)
- [x] Клиент официального API (OAuth2 `client_credentials`, инъекция HTTP-клиента)
- [x] Тулза `official_api_call` с обработкой ошибок через `ToolError`
- [x] In-memory тесты (`Client(mcp)`) + `httpx.MockTransport` — 26 тестов, ruff + mypy чисты
- [ ] Парсинг-тулзы (`search_listings`, `get_listing`) — слой обхода антибота
      (браузер + прокси), **без** «лобового» обхода капчи
- [ ] `lifespan` под пул соединений (когда появится БД/Redis)
- [ ] Порог HTTP-транспорта: сервер нужен удалённо → `mcp.http_app()` + `JWTVerifier`

## Этап 2 — skills

- [ ] Финализировать каждый скил по `superpowers:writing-skills`
      (RED→GREEN→REFACTOR на субагентах)
- [ ] `description` = что + КОГДА, с trigger-словами
- [ ] Тело < 500 строк, детали в `references/`, детерминированные операции — в тулзы
- [ ] Пресс-тестирование `avito-legal-guardrails` как discipline-скила

## Этап 3 — упаковка в Claude Code plugin

- [ ] `claude plugin validate ./` — проверка манифеста и frontmatter
- [ ] `claude --plugin-dir ./` + `/reload-plugins` — локальная отладка
- [ ] `.mcp.json` в плоском формате; переключение dev → `uvx` после публикации

## Этап 4 — переносимость

- [ ] Проверить подключение к Cursor / Codex / Gemini CLI (см. [`portability.md`](portability.md))
- [ ] Опционально: тонкие адаптеры `.cursor-plugin/`, `.codex-plugin/`
- [ ] Опционально: `SkillsProvider` в сервере (раздача skills по MCP)

## Этап 5 — CI/CD и публикация

- [ ] GitHub Actions: `ruff` + `mypy` + `pytest` на PR
- [ ] Публикация в PyPI по тегу (Trusted Publishing / OIDC — без хранения токена)
- [ ] Синхронизировать `plugin.json.version` и `pyproject.toml.version`
- [ ] `LICENSE` (MIT), `.gitignore`

## Триггеры смены решений

- Тулз > 20–25 → точность выбора тулзы падает; разбить на focused-серверы.
- Нужен remote/мультиюзер → streamable HTTP + JWT + Docker + reverse proxy (TLS).
- Codex как таргет + HTTP → нужен `mcp-proxy`.
- Нужны build-hooks/VCS-версии → сменить `uv_build` на `hatchling`.
