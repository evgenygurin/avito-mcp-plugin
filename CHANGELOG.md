# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [семантическому версионированию](https://semver.org/lang/ru/).

## [Unreleased]

### Added

- Доменные Pydantic-модели: `Listing`, `SearchQuery`, `SearchResult`.
- Утилита `extract_listing_id` (id объявления из URL или «голого» id).
- Клиент официального API (`AvitoOfficialClient`, OAuth2 `client_credentials`,
  инъекция HTTP-клиента для тестируемости).
- MCP-тулза `official_api_call` (свои объявления; ошибки через `ToolError`).
- Тестовый слой: 26 тестов через in-memory `Client(mcp)` и `httpx.MockTransport`;
  ruff + mypy чисты.
- Зависимость `httpx`.

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

[Unreleased]: https://github.com/evgenygurin/avito-mcp-plugin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/evgenygurin/avito-mcp-plugin/releases/tag/v0.1.0
