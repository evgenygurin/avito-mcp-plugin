"""ORM-модели хранилища (SQLAlchemy 2.0, схема ``avito`` в Postgres Supabase).

Схема ``avito`` намеренно отдельная от ``public`` и закрыта от Data API: плагин
ходит в базу по DSN со своей машины, публичного клиента у него нет.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "avito"


class Base(DeclarativeBase):
    """Общий базовый класс деклараций."""


class SeenItem(Base):
    """Объявление, которое парсер уже видел (dedup)."""

    __tablename__ = "seen_items"
    __table_args__ = {"schema": SCHEMA}

    # id приходит снаружи (идентификатор объявления Avito) — не автогенерируется.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    url: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    # Numeric отдаёт Decimal, а не float — деньги, округление float здесь
    # недопустимо. Аннотация должна отражать фактический рантайм-тип ORM.
    price: Mapped[Decimal | None] = mapped_column(Numeric)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PriceHistory(Base):
    """Точка истории цены: строка на каждое наблюдение."""

    __tablename__ = "price_history"
    __table_args__ = {"schema": SCHEMA}

    # GENERATED ALWAYS AS IDENTITY, а не BIGSERIAL: так колонка создана в базе,
    # и декларация должна совпадать со схемой, иначе генерация миграций начнёт
    # выдавать ложные различия.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(f"{SCHEMA}.seen_items.id", ondelete="CASCADE")
    )
    price: Mapped[Decimal] = mapped_column(Numeric)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProxyCooldown(Base):
    """Прокси, отдавший блокировку: пул не тратит на него попытки до конца TTL.

    Хранится адрес БЕЗ учётных данных — пароли прокси в базу не попадают.
    """

    __tablename__ = "proxy_cooldown"
    __table_args__ = {"schema": SCHEMA}

    proxy: Mapped[str] = mapped_column(String, primary_key=True)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
