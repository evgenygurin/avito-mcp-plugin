"""Доменные Pydantic-модели плагина (structured output тулз)."""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Listing(BaseModel):
    """Объявление Avito. Только фактические поля (без ПДн продавца)."""

    id: int
    title: str
    price: float | None = None
    url: str | None = None
    region: str | None = None
    seller_type: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class SearchQuery(BaseModel):
    """Параметры поиска объявлений."""

    query: NonEmptyStr
    region: str | None = None
    limit: int = Field(default=50, gt=0, le=100)


class SearchResult(BaseModel):
    """Результат поиска: список объявлений и их количество."""

    items: list[Listing]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.items)


class OwnItem(BaseModel):
    """Своё объявление из официального API (core/v1/items).

    Форма ответа Avito варьируется — все поля кроме ``id`` опциональны,
    неизвестные ключи игнорируются (устойчивость к изменениям API).
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str | None = None
    status: str | None = None
    url: str | None = None
    price: float | None = None
    category: str | None = None


class OwnItemsResult(BaseModel):
    """Список своих объявлений и их количество."""

    items: list[OwnItem]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def count(self) -> int:
        return len(self.items)


class AccountInfo(BaseModel):
    """Свой аккаунт (core/v1/accounts/self).

    Возвращаем ``id`` (user_id для статистики) и отображаемое ``name``.
    ПДн (email/phone) намеренно не включены — минимизация по 152-ФЗ.
    """

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None
