"""Фильтрация объявлений по ключевым словам, продавцу, цене, гео, возрасту."""

from .filters import FilterSpec, apply_filters

__all__ = ["FilterSpec", "apply_filters"]
