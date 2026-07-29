"""Unit tests for pure session helpers (no persistence, no service).

The session/persistence contract (create/load/add_message round-trips) is
tested in crow-memory, which owns the storage layer. Here we only cover the
pure helpers that live in crow_cli.agent.session.
"""

from crow_cli.agent.session import _parse_frontmatter, get_skills


class TestParseFrontmatter:
    """Frontmatter is parsed with PyYAML, not a hand-rolled parser."""

    def test_simple_mapping(self):
        meta = _parse_frontmatter("---\nname: x\ndescription: y\n---\nbody")
        assert meta == {"name": "x", "description": "y"}

    def test_folded_scalar_and_extra_keys(self):
        text = "---\nname: x\ndescription: >-\n  folded\n  text.\nversion: 2\n---\nbody"
        meta = _parse_frontmatter(text)
        assert meta["description"] == "folded text."
        assert meta["version"] == 2

    def test_no_frontmatter_returns_none(self):
        assert _parse_frontmatter("# just markdown") is None

    def test_invalid_yaml_returns_none(self):
        assert _parse_frontmatter('---\nname: "unclosed\n---\n') is None

    def test_non_mapping_returns_none(self):
        assert _parse_frontmatter("---\n- a\n- b\n---\n") is None


class TestGetSkills:
    """get_skills returns structured skills and skips invalid entries."""

    def _mk(self, root, name, content):
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(content)

    def test_returns_structured_skills(self, tmp_path):
        self._mk(tmp_path, "alpha", "---\nname: alpha\ndescription: first\n---\n")
        self._mk(tmp_path, "beta", "---\nname: beta\ndescription: second\n---\n")
        skills = {s["name"]: s for s in get_skills(tmp_path)}
        assert set(skills) == {"alpha", "beta"}
        assert skills["alpha"]["description"] == "first"
        assert skills["alpha"]["path"].endswith("alpha/SKILL.md")

    def test_skips_invalid_entries(self, tmp_path):
        self._mk(tmp_path, "good", "---\nname: good\ndescription: ok\n---\n")
        self._mk(tmp_path, "no-name", "---\ndescription: missing name\n---\n")
        self._mk(tmp_path, "no-fm", "# no frontmatter\n")
        self._mk(tmp_path, "bad-yaml", '---\nname: "unclosed\n---\n')
        (tmp_path / "stray-file").write_text("not a skill dir")
        assert {s["name"] for s in get_skills(tmp_path)} == {"good"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert get_skills(tmp_path / "does-not-exist") == []
