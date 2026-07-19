"""Тесты хранилища на SQLAlchemy ORM.

Две группы:
- чистые проверки схемы и нормализации DSN — без базы;
- поведение хранилища против **настоящего** Postgres проекта Supabase; они
  пропускаются, если ``AVITO_SUPABASE_DSN`` не задан. Подменять Postgres другой
  СУБД в тестах нельзя: диалектные upsert и ``timestamptz`` там ведут себя иначе,
  и зелёные тесты ничего не доказывали бы.
"""

from __future__ import annotations

import os
import time
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from avito_mcp_server.storage.models import PriceHistory, ProxyCooldown, SeenItem
from avito_mcp_server.storage.supabase import SeenRow, SupabaseStorage, normalize_dsn

DSN = os.getenv("AVITO_SUPABASE_DSN", "").strip()
requires_db = pytest.mark.skipif(not DSN, reason="AVITO_SUPABASE_DSN не задан")


class TestSchema:
    """Метаданные ORM — база не нужна."""

    def test_tables_live_in_avito_schema(self) -> None:
        # public закрыт намеренно: схема avito не выставлена в Data API.
        assert SeenItem.__table__.schema == "avito"
        assert PriceHistory.__table__.schema == "avito"
        assert ProxyCooldown.__table__.schema == "avito"

    def test_seen_item_id_is_not_autoincrement(self) -> None:
        # id — идентификатор объявления Avito, приходит снаружи.
        assert SeenItem.__table__.c.id.autoincrement is False

    def test_price_history_id_is_identity_not_serial(self) -> None:
        # В базе колонка создана как GENERATED ALWAYS AS IDENTITY. Если ORM
        # объявит BIGSERIAL, декларации разъедутся со схемой и генерация
        # миграций начнёт выдавать ложные различия.
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable

        ddl = str(
            CreateTable(PriceHistory.__table__).compile(dialect=postgresql.dialect())
        )
        assert "GENERATED ALWAYS AS IDENTITY" in ddl
        assert "SERIAL" not in ddl

    def test_price_history_cascades_from_seen_items(self) -> None:
        (fk,) = list(PriceHistory.__table__.c.item_id.foreign_keys)
        assert fk.ondelete == "CASCADE"


class TestNormalizeDsn:
    def test_adds_psycopg_driver(self) -> None:
        # Кабинет Supabase отдаёт postgresql://, иначе SQLAlchemy возьмёт psycopg2.
        assert normalize_dsn("postgresql://u:p@h:5432/db").startswith(
            "postgresql+psycopg://u:p@h:5432/db"
        )

    def test_upgrades_legacy_postgres_scheme(self) -> None:
        assert normalize_dsn("postgres://u:p@h:5432/db").startswith(
            "postgresql+psycopg://"
        )

    def test_keeps_explicit_driver(self) -> None:
        # Драйвер не переписываем; sslmode дописывается, если его не задали.
        dsn = "postgresql+psycopg://u:p@h:5432/db"
        assert normalize_dsn(dsn).startswith(dsn)
        assert "postgresql+psycopg://" in normalize_dsn(dsn)


def _purge(storage: SupabaseStorage) -> None:
    """Убрать тестовые данные из общей базы (id из зарезервированного диапазона)."""
    with storage.engine.begin() as conn:
        conn.execute(text("DELETE FROM avito.seen_items WHERE id >= 999000000"))
        conn.execute(text("DELETE FROM avito.proxy_cooldown WHERE proxy LIKE 'test-%'"))


@requires_db
class TestAgainstPostgres:
    """Поведение против живой базы Supabase."""

    @pytest.fixture
    def store(self) -> SupabaseStorage:
        storage = SupabaseStorage(DSN)
        # Чистим ДО теста, а не только после: база общая и живая, и остатки от
        # прерванного прогона (или от параллельной сессии) отравляли следующий
        # — история цены приходила длиннее ожидаемой, и падали разные тесты
        # при неизменном коде.
        _purge(storage)
        yield storage
        _purge(storage)

    def test_first_upsert_reports_new_item(self, store: SupabaseStorage) -> None:
        assert store.upsert_seen(999000001, "/x_1", "квартира", 50000.0) is True
        assert store.upsert_seen(999000001, "/x_1", "квартира", 49000.0) is False

    def test_price_updates_and_history_accumulates(
        self, store: SupabaseStorage
    ) -> None:
        store.upsert_seen(999000002, "/x_2", "квартира", 50000.0)
        store.upsert_seen(999000002, "/x_2", "квартира", 45000.0)

        assert store.get_previous_price(999000002) == 45000.0
        history = store.get_price_history(999000002)
        assert [price for price, _ in history] == [45000.0, 50000.0]
        # Наружу — epoch-float, а не datetime: иначе поедут модели тулз.
        assert all(isinstance(seen_at, float) for _, seen_at in history)

    def test_upsert_without_price_skips_history(self, store: SupabaseStorage) -> None:
        store.upsert_seen(999000003, "/x_3", "гараж", None)
        assert store.get_price_history(999000003) == []

    def test_unknown_item_has_no_price(self, store: SupabaseStorage) -> None:
        assert store.get_previous_price(999999999) is None

    def test_list_seen_ids_contains_written_item(self, store: SupabaseStorage) -> None:
        store.upsert_seen(999000004, "/x_4", "квартира", 1000.0)
        assert 999000004 in store.list_seen_ids()

    def test_proxy_cooldown_roundtrip(self, store: SupabaseStorage) -> None:
        store.mark_proxy_blocked("test-h1:1")
        store.mark_proxy_blocked("test-h1:1")  # повтор не должен падать на PK

        assert "test-h1:1" in store.blocked_proxies(ttl=1800)
        # TTL истёк — адрес снова в игре.
        assert "test-h1:1" not in store.blocked_proxies(ttl=0)

    def test_forget_proxy_removes_it(self, store: SupabaseStorage) -> None:
        store.mark_proxy_blocked("test-h2:2")
        store.forget_proxy("test-h2:2")
        assert "test-h2:2" not in store.blocked_proxies(ttl=1800)

    def test_history_survives_repeated_scans(self, store: SupabaseStorage) -> None:
        for price in (100.0, 90.0, 80.0):
            store.upsert_seen(999000005, "/x_5", "квартира", price)
            time.sleep(0.01)  # порядок по seen_at должен быть устойчивым
        assert [p for p, _ in store.get_price_history(999000005)] == [80.0, 90.0, 100.0]

    def test_fetch_seen_distinguishes_absent_from_priceless(
        self, store: SupabaseStorage
    ) -> None:
        # Ключевая семантика: наличие ключа = «видели раньше», значение = цена.
        # Объявление без цены существует, но цены не имеет — этого различия
        # не давал get_previous_price, из-за чего новизну приходилось узнавать
        # отдельным запросом.
        store.upsert_seen(999000010, "/x_10", "с ценой", 500.0)
        store.upsert_seen(999000011, "/x_11", "без цены", None)

        seen = store.fetch_seen([999000010, 999000011, 999999998])

        assert seen[999000010] == 500.0
        assert 999000011 in seen and seen[999000011] is None
        assert 999999998 not in seen

    def test_fetch_seen_on_empty_input_makes_no_query(
        self, store: SupabaseStorage
    ) -> None:
        assert store.fetch_seen([]) == {}

    def test_upsert_seen_many_inserts_and_updates_in_one_call(
        self, store: SupabaseStorage
    ) -> None:
        store.upsert_seen_many(
            [
                SeenRow(id=999000012, url="/x_12", title="первое", price=100.0),
                SeenRow(id=999000013, url="/x_13", title="второе", price=200.0),
            ]
        )
        assert store.fetch_seen([999000012, 999000013]) == {
            999000012: 100.0,
            999000013: 200.0,
        }

        # Повторный батч обновляет цену и продлевает историю.
        store.upsert_seen_many(
            [SeenRow(id=999000012, url="/x_12", title="первое", price=90.0)]
        )
        assert store.fetch_seen([999000012])[999000012] == 90.0
        assert [p for p, _ in store.get_price_history(999000012)] == [90.0, 100.0]

    def test_upsert_seen_many_skips_history_for_priceless_rows(
        self, store: SupabaseStorage
    ) -> None:
        store.upsert_seen_many(
            [SeenRow(id=999000014, url="/x_14", title="гараж", price=None)]
        )
        assert store.get_price_history(999000014) == []
        assert 999000014 in store.fetch_seen([999000014])

    def test_upsert_seen_many_survives_duplicate_id_in_same_batch(
        self, store: SupabaseStorage
    ) -> None:
        # Публичный метод сегодня корректен только потому, что дедуп живёт в
        # parser.walk_pages — вызывающий, не гарантирующий уникальность id
        # внутри одного батча, роняет ВСЮ транзакцию на
        # "ON CONFLICT DO UPDATE command cannot affect row a second time".
        # Хранилище не должно зависеть от инварианта другого модуля.
        store.upsert_seen_many(
            [
                SeenRow(id=999000015, url="/x_15", title="старое", price=100.0),
                SeenRow(id=999000015, url="/x_15", title="новое", price=90.0),
            ]
        )
        assert store.fetch_seen([999000015]) == {999000015: 90.0}

    def test_upsert_seen_many_on_empty_input_is_noop(
        self, store: SupabaseStorage
    ) -> None:
        store.upsert_seen_many([])  # не должно падать на пустом VALUES

    def test_price_columns_are_decimal_at_runtime(self, store: SupabaseStorage) -> None:
        # Context7-аудит (SQLAlchemy 2.0.51): колонки объявлены Numeric, но
        # аннотации Mapped[float] — mypy валидирует код, который на самом деле
        # получает Decimal и упадёт TypeError на "Decimal + float". Маскируется
        # только тем, что оба места чтения в SupabaseStorage оборачивают в
        # float() на границе. Тест фиксирует фактический рантайм-тип ORM.
        store.upsert_seen_many(
            [SeenRow(id=999000016, url="/x_16", title="дом", price=123.0)]
        )
        with store._session() as session:
            seen_item = session.get(SeenItem, 999000016)
            assert isinstance(seen_item.price, Decimal)
            (history_row,) = (
                session.execute(
                    select(PriceHistory).where(PriceHistory.item_id == 999000016)
                )
                .scalars()
                .all()
            )
            assert isinstance(history_row.price, Decimal)


class TestEngineSetup:
    """Как настраивается подключение — без реальной базы."""

    def test_engine_is_reused_between_instances(self, monkeypatch) -> None:
        # build_storage() зовётся на каждый вызов тулзы: без кеша каждый раз
        # создавался бы новый пул соединений, который никто не закрывает.
        import avito_mcp_server.storage.supabase as mod

        mod.reset_engine_cache()
        created: list[str] = []
        monkeypatch.setattr(
            mod, "create_engine", lambda url, **kw: created.append(url) or object()
        )

        a = SupabaseStorage("postgresql://u:p@h:5432/db")
        b = SupabaseStorage("postgresql://u:p@h:5432/db")
        assert len(created) == 1
        assert a.engine is b.engine

    def test_engine_options_survive_idle_and_pooler(self, monkeypatch) -> None:
        import avito_mcp_server.storage.supabase as mod

        mod.reset_engine_cache()
        captured: dict = {}

        def _fake(url, **kw):
            captured.update(kw)
            return object()

        monkeypatch.setattr(mod, "create_engine", _fake)
        SupabaseStorage("postgresql://u:p@h:5432/db")

        # Supabase рвёт простаивающие соединения — без ping первый запрос упадёт.
        assert captured["pool_pre_ping"] is True
        # Transaction pooler (6543) несовместим с prepared statements psycopg.
        assert captured["connect_args"]["prepare_threshold"] is None
        # Без таймаута недоступная база даёт зависание вместо ошибки.
        assert captured["connect_args"]["connect_timeout"] > 0


class TestDsnSecurity:
    def test_sslmode_defaults_to_require(self) -> None:
        # libpq по умолчанию берёт `prefer` — молча откатывается в открытый текст.
        assert "sslmode=require" in normalize_dsn("postgresql://u:p@h:5432/db")

    def test_explicit_sslmode_is_kept(self) -> None:
        dsn = normalize_dsn("postgresql://u:p@h:5432/db?sslmode=verify-full")
        assert "sslmode=verify-full" in dsn
        assert dsn.count("sslmode") == 1
