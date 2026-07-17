"""Тесты раздачи skills по MCP (SkillsProvider)."""

import pytest
from fastmcp import Client, FastMCP

from avito_mcp_server.skills_provider import register_skills, resolve_skills_dir


class TestResolveSkillsDir:
    def test_finds_repo_skills_in_dev(self) -> None:
        d = resolve_skills_dir()
        assert d is not None
        assert (d / "using-avito-mcp" / "SKILL.md").exists()

    def test_env_override_missing_dir_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        monkeypatch.setenv("AVITO_SKILLS_DIR", str(tmp_path) + "/nope")
        assert resolve_skills_dir() is None


class TestRegisterSkills:
    async def test_skills_served_as_resources(self) -> None:
        mcp: FastMCP = FastMCP("t")
        assert register_skills(mcp) is True
        async with Client(mcp) as client:
            uris = [str(r.uri) for r in await client.list_resources()]
        assert any("using-avito-mcp" in u for u in uris)
        assert any("scraping-avito" in u for u in uris)

    async def test_skill_content_readable(self) -> None:
        mcp: FastMCP = FastMCP("t")
        register_skills(mcp)
        async with Client(mcp) as client:
            uris = [str(r.uri) for r in await client.list_resources()]
            skill_md = next(
                u for u in uris if "using-avito-mcp" in u and u.endswith("SKILL.md")
            )
            content = await client.read_resource(skill_md)
        assert "using-avito-mcp" in content[0].text

    def test_register_false_when_no_skills(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        monkeypatch.setenv("AVITO_SKILLS_DIR", str(tmp_path) + "/nope")
        mcp: FastMCP = FastMCP("t")
        assert register_skills(mcp) is False
