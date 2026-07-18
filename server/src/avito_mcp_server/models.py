"""Доменные Pydantic-модели плагина (structured output тулз)."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class Listing(BaseModel):
    """Объявление Avito. Только фактические поля (без ПДн продавца).

    Телефоны/имена продавцов намеренно не моделируются: сбор контактов третьих
    лиц — ПДн, вне области плагина.
    """

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
    """Результат поиска: список объявлений и их количество."""

    items: list[Listing]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.items)


class ProxyHealth(BaseModel):
    """Результат диагностики прокси/кук (пробный запрос к Avito)."""

    ok: bool
    cookie_provider: str
    proxy_type: str
    detail: str
