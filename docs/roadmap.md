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

- [x] Финализированы все 4 скила по `superpowers:writing-skills`
- [x] RED-baseline на субагентах (3 сценария): вывод — сильная модель уже
      compliant в явных и тонких кейсах; скилы работают как **reference-guardrails
      для переносимости** (на слабые агенты) и фиксации проектной политики
- [x] Verify: субагент цитирует конкретные пороги/Red Flags из скилов; закрыты
      выявленные пробелы (объём аналитики, легальные альтернативы контакта)
- [x] Ревью качества (skill-reviewer): описания = WHEN, markdown-ссылки вместо
      `[[…]]`, docs-указатели; тела 312–625 слов
- [ ] Повторное пресс-тестирование при переносе на слабые модели/harness
- [ ] Дополнить скилы примерами вызова после реализации парсинг-тулз

## Этап 3 — упаковка в Claude Code plugin

- [x] `claude plugin validate ./` — PASS (plugin + marketplace манифесты; 1 minor warning)
- [x] Структура: плоский `.mcp.json`, компоненты в корне, версии синхронны (0.1.0)
- [x] End-to-end: плагинная stdio-команда из `.mcp.json` запускает сервер с
      тулзами `ping` + `official_api_call` (проверено FastMCP-клиентом)
- [x] Валидация через агент `plugin-dev:plugin-validator`: 0 critical, 0 major
- [ ] Интерактивная `claude --plugin-dir ./` + `/reload-plugins` — требует
      интерактивной сессии (эквивалент проверен через stdio)
- [ ] Переключение dev → `uvx` после публикации в PyPI (Этап 5)

> **Known warning:** `CLAUDE.md` в корне не грузится как install-time контекст
> (нужен для разработки репо; guardrails продублированы в `avito-legal-guardrails`).
> Принято осознанно.

## Этап 4 — переносимость

- [x] Готовые конфиги MCP для Cursor/Codex/Gemini/VS Code —
      [`examples/mcp-configs/`](../examples/mcp-configs/) (валидированы JSON/TOML)
- [x] Тонкие адаптеры: [`.cursor-plugin/plugin.json`](../.cursor-plugin/plugin.json),
      [`.codex/INSTALL.md`](../.codex/INSTALL.md)
- [x] `SkillsProvider` в сервере: раздача `skills/` по MCP (`skill://<name>/…`),
      проверено end-to-end через stdio (8 ресурсов); 32 теста
- [ ] Живая проверка подключения к Cursor/Codex/Gemini (нужны сами агенты)

## Этап 5 — релиз-подготовка и публикация

- [x] `LICENSE` (MIT), `.gitignore`, `.env.example`
- [x] Скрипт синхронизации версий [`scripts/check_versions.py`](../scripts/check_versions.py)
      (5 манифестов; проверено на pass и на ловле рассинхрона)
- [x] Документация процесса релиза/публикации — [`releasing.md`](releasing.md)
- [ ] GitHub Actions: `ruff` + `mypy` + `pytest` на PR (**отложено**)
- [ ] Публикация в PyPI по тегу (Trusted Publishing / OIDC) — после готовности
      парсинг-тулз и первого стабильного релиза
- [ ] Переключение `.mcp.json` и примеров dev → `uvx avito-mcp-server` после
      первой публикации в PyPI

## Триггеры смены решений

- Тулз > 20–25 → точность выбора тулзы падает; разбить на focused-серверы.
- Нужен remote/мультиюзер → streamable HTTP + JWT + Docker + reverse proxy (TLS).
- Codex как таргет + HTTP → нужен `mcp-proxy`.
- Нужны build-hooks/VCS-версии → сменить `uv_build` на `hatchling`.
