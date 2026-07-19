"""Хранилище парсера в Postgres (Supabase) через SQLAlchemy ORM.

Единственный бэкенд: dedup объявлений, история цены, cooldown прокси.

Наружу время отдаётся epoch-float — модели тулз (`PricePoint`) ждут число, а не
``datetime``. Внутри лежит ``timestamptz``, конвертация — на границе.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, bindparam, create_engine, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from .models import PriceHistory, ProxyCooldown, SeenItem
from .rows import SeenRow

log = logging.getLogger(__name__)

__all__ = [
    "SeenRow",
    "SupabaseStorage",
    "get_engine",
    "normalize_dsn",
    "reset_engine_cache",
]


def normalize_dsn(dsn: str) -> str:
    """Привести DSN Supabase к драйверу psycopg 3 и потребовать TLS.

    Кабинет отдаёт строку вида ``postgresql://…``; SQLAlchemy по умолчанию
    подставил бы psycopg2, которого в зависимостях нет. Плюс libpq без явного
    ``sslmode`` использует ``prefer`` — молча откатывается на незашифрованное
    соединение, что для облачной базы недопустимо.
    """
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    elif dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql+psycopg://", 1)

    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


# Engine кеширован по DSN: build_storage() вызывается на каждый вызов тулзы,
# а каждый Engine — это отдельный пул соединений, который никто не закрывает.
_ENGINES: dict[str, Engine] = {}


def reset_engine_cache() -> None:
    """Сбросить кеш движков (для тестов и смены конфигурации)."""
    for engine in _ENGINES.values():
        with suppress(Exception):
            engine.dispose()
    _ENGINES.clear()


def get_engine(dsn: str) -> Engine:
    """Получить общий Engine для DSN, создав его при первом обращении."""
    url = normalize_dsn(dsn)
    engine = _ENGINES.get(url)
    if engine is None:
        engine = create_engine(
            url,
            # Supabase закрывает простаивающие соединения — без ping первый
            # запрос после паузы падал бы на мёртвом соединении из пула.
            pool_pre_ping=True,
            connect_args={
                # Transaction pooler Supabase (порт 6543) не поддерживает
                # prepared statements psycopg — с ними соединение ломается.
                "prepare_threshold": None,
                # Без таймаута недоступная база даёт зависание вместо ошибки.
                "connect_timeout": 10,
            },
        )
        _ENGINES[url] = engine
    return engine


def _epoch(value: Any) -> float:
    """``timestamptz`` → epoch-float; число отдаём как есть."""
    return value.timestamp() if isinstance(value, datetime) else float(value)


class SupabaseStorage:
    """Хранилище в схеме ``avito`` проекта Supabase."""

    def __init__(self, dsn: str, engine: Engine | None = None) -> None:
        self.engine = engine if engine is not None else get_engine(dsn)
        self._session_factory = sessionmaker(bind=self.engine)

    def _session(self) -> Session:
        return self._session_factory()

    def fetch_seen(self, item_ids: Iterable[int]) -> dict[int, float | None]:
        """Известные объявления из числа запрошенных: ``{id: последняя цена}``.

        Наличие ключа означает «видели раньше», значение — цену (``None``, если
        объявление без цены). Одним запросом на всю страницу каталога вместо
        запроса на объявление: база облачная, и round-trip дороже самой выборки.
        """
        ids = list(item_ids)
        if not ids:
            return {}
        with self._session() as session:
            rows = session.execute(
                select(SeenItem.id, SeenItem.price).where(SeenItem.id.in_(ids))
            ).all()
        return {
            int(item_id): None if price is None else float(price)
            for item_id, price in rows
        }

    def upsert_seen_many(self, rows: Sequence[SeenRow]) -> None:
        """Вставить/обновить пачку объявлений и дописать историю цены.

        Объявления и точки истории идут одной транзакцией: иначе при сбое
        история разъедется с ``seen_items``.

        Дедуп по id внутри батча — на случай дубля в одной странице каталога:
        Postgres запрещает ``ON CONFLICT DO UPDATE`` дважды задевать одну
        строку в пределах ОДНОГО multi-row ``VALUES`` (``CardinalityViolation``).
        Поэтому это executemany — N отдельных однострочных upsert в одной
        транзакции, а не один multi-row ``INSERT``: при дубле id внутри батча
        побеждает последняя запись, а не падение всей транзакции. Сегодня
        источник (``parser.walk_pages``) сам дедупит объявления по id, но
        хранилище не должно зависеть от инварианта другого модуля.
        """
        if not rows:
            return
        deduped: dict[int, SeenRow] = {row.id: row for row in rows}
        stmt = (
            insert(SeenItem)
            .values(
                id=bindparam("id"),
                url=bindparam("url"),
                title=bindparam("title"),
                price=bindparam("price"),
                first_seen=func.now(),
                last_seen=func.now(),
            )
            .on_conflict_do_update(
                index_elements=[SeenItem.id],
                set_={
                    "url": bindparam("url"),
                    "title": bindparam("title"),
                    "price": bindparam("price"),
                    "last_seen": func.now(),
                },
            )
        )
        with self._session() as session, session.begin():
            session.execute(
                stmt,
                [
                    {
                        "id": row.id,
                        "url": row.url,
                        "title": row.title,
                        "price": row.price,
                    }
                    for row in deduped.values()
                ],
            )
            # Без цены точка истории бессмысленна.
            session.add_all(
                [
                    PriceHistory(item_id=row.id, price=row.price)
                    for row in deduped.values()
                    if row.price is not None
                ]
            )

    def upsert_seen(
        self,
        item_id: int,
        url: str | None,
        title: str | None,
        price: float | None,
    ) -> bool:
        """Вставить/обновить одно объявление. ``True`` — видим впервые."""
        is_new = item_id not in self.fetch_seen([item_id])
        self.upsert_seen_many([SeenRow(id=item_id, url=url, title=title, price=price)])
        return is_new

    def get_previous_price(self, item_id: int) -> float | None:
        """Последняя известная цена объявления (или ``None``)."""
        return self.fetch_seen([item_id]).get(item_id)

    def list_seen_ids(self) -> set[int]:
        with self._session() as session:
            rows = session.execute(select(SeenItem.id)).scalars().all()
        return {int(row) for row in rows}

    def get_price_history(self, item_id: int) -> list[tuple[float, float]]:
        """История цены, свежая первой: список ``(цена, время)``."""
        with self._session() as session:
            rows = session.execute(
                select(PriceHistory.price, PriceHistory.seen_at)
                .where(PriceHistory.item_id == item_id)
                .order_by(PriceHistory.seen_at.desc())
            ).all()
        return [(float(price), _epoch(seen_at)) for price, seen_at in rows]

    def mark_proxy_blocked(self, proxy: str) -> None:
        """Запомнить адрес, отдавший блокировку."""
        with self._session() as session, session.begin():
            session.execute(
                insert(ProxyCooldown)
                .values(proxy=proxy, blocked_at=func.now())
                .on_conflict_do_update(
                    index_elements=[ProxyCooldown.proxy],
                    set_={"blocked_at": func.now()},
                )
            )

    def blocked_proxies(self, ttl: float) -> set[str]:
        """Адреса, заблокированные не позже ``ttl`` секунд назад."""
        cutoff = datetime.now(UTC) - timedelta(seconds=float(ttl))
        with self._session() as session:
            rows = (
                session.execute(
                    select(ProxyCooldown.proxy).where(ProxyCooldown.blocked_at > cutoff)
                )
                .scalars()
                .all()
            )
        return set(rows)

    def forget_proxy(self, proxy: str) -> None:
        """Убрать адрес из cooldown (напр. после успешного запроса через него)."""
        with self._session() as session, session.begin():
            session.execute(delete(ProxyCooldown).where(ProxyCooldown.proxy == proxy))
