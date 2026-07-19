"""Хранилище парсера: Postgres (Supabase) через SQLAlchemy ORM."""

from .models import Base, PriceHistory, ProxyCooldown, SeenItem
from .supabase import SupabaseStorage, normalize_dsn

__all__ = [
    "Base",
    "PriceHistory",
    "ProxyCooldown",
    "SeenItem",
    "SupabaseStorage",
    "normalize_dsn",
]
