"""Тесты общих утилит композиции (роли, неймспейсы)."""

from avito_mcp_shared.roles import ROLE_NAMESPACES, ServerRole


def test_server_roles_exist() -> None:
    assert ServerRole.GATEWAY == "gateway"
    assert ServerRole.SCRAPER == "scraper"
    assert ServerRole.DB == "db"
    assert ServerRole.NOTIFY == "notify"


def test_role_namespace_map_covers_all_components() -> None:
    """Каждому монтируемому компоненту (кроме gateway-движка) есть неймспейс."""
    assert set(ROLE_NAMESPACES) == {
        ServerRole.SCRAPER,
        ServerRole.DB,
        ServerRole.NOTIFY,
    }


def test_namespaces_are_lowercase_identifiers() -> None:
    for role, ns in ROLE_NAMESPACES.items():
        assert ns.islower(), f"{role}: неймспейс должен быть lowercase"
        assert ns.replace("_", "").isalnum(), f"{role}: не валидный идентификатор"