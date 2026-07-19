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
    description: str | None = None


class SearchResult(BaseModel):
    """Результат поиска: список объявлений и их количество."""

    items: list[Listing]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.items)


class ProxyProbe(BaseModel):
    """Итог проверки одного адреса из пула прокси (без учётных данных)."""

    proxy: str
    ok: bool
    detail: str


class ProxyHealth(BaseModel):
    """Результат диагностики прокси/кук (пробный запрос к Avito)."""

    ok: bool
    cookie_provider: str
    proxy_type: str
    detail: str
    probes: list[ProxyProbe] = Field(default_factory=list)


class ScanItem(BaseModel):
    """Одно объявление из результата scan_new_listings."""

    listing: Listing
    is_new: bool
    price_delta: float | None = None


class ScanResult(BaseModel):
    """Результат сканирования: новые и подешевевшие объявления."""

    items: list[ScanItem]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.items)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def new_count(self) -> int:
        return sum(1 for i in self.items if i.is_new)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dropped_count(self) -> int:
        return sum(1 for i in self.items if not i.is_new)


class PricePoint(BaseModel):
    """Одна запись истории цены."""

    price: float
    seen_at: float


class PriceHistoryResult(BaseModel):
    """История цены объявления."""

    listing_id: int
    history: list[PricePoint]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.history)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def latest_price(self) -> float | None:
        return self.history[0].price if self.history else None


class ExportResult(BaseModel):
    """Результат экспорта объявлений."""

    format: str
    path: str | None = None
    content: str | None = None
    count: int = 0


class NotificationResult(BaseModel):
    """Результат отправки уведомления."""

    channel: str
    sent: bool
    targets: list[str] = Field(default_factory=list)
    detail: str = ""
