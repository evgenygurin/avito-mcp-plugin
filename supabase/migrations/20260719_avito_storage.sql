-- Хранилище парсера Avito: dedup объявлений, история цены, память о выжженных IP.
--
-- Схема `avito` намеренно отдельная и НЕ выставляется в Data API: плагин ходит
-- в базу серверным ключом со своей машины, публичного клиента у него нет.
-- RLS включён на всех таблицах как defense in depth — если схему когда-нибудь
-- откроют в Data API, доступ не появится сам собой.

create schema if not exists avito;

-- Объявления, которые парсер уже видел. id — идентификатор объявления Avito,
-- поэтому bigint без генерации: он приходит снаружи.
create table if not exists avito.seen_items (
    id         bigint primary key,
    url        text,
    title      text,
    price      numeric,
    first_seen timestamptz not null default now(),
    last_seen  timestamptz not null default now()
);

-- История цены: строка на каждое изменение, из неё считается «подешевело».
create table if not exists avito.price_history (
    id      bigint generated always as identity primary key,
    item_id bigint      not null references avito.seen_items (id) on delete cascade,
    price   numeric     not null,
    seen_at timestamptz not null default now()
);

create index if not exists idx_ph_item_id on avito.price_history (item_id);
create index if not exists idx_ph_seen_at on avito.price_history (item_id, seen_at desc);

-- Прокси, отдавшие блокировку: пул не тратит на них попытки, пока не истечёт TTL.
-- Хранится адрес без учётных данных — пароли в БД не кладём.
create table if not exists avito.proxy_cooldown (
    proxy      text primary key,
    blocked_at timestamptz not null default now()
);

create index if not exists idx_cooldown_blocked_at on avito.proxy_cooldown (blocked_at desc);

alter table avito.seen_items     enable row level security;
alter table avito.price_history  enable row level security;
alter table avito.proxy_cooldown enable row level security;

-- Политик намеренно нет: с включённым RLS и без политик доступ есть только у
-- service_role (он обходит RLS). Anon/authenticated не получают ничего — это и
-- нужно, у плагина нет пользовательских сессий.
revoke all on all tables in schema avito from anon, authenticated;
revoke all on schema avito from anon, authenticated;
