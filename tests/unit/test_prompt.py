"""Unit tests for prompt context assembly — skills catalog and AGENTS.md rules.

These live apart from ``test_session.py`` because they cover prompt *content*
(what gets put in front of the model), not session lifecycle. The system-prompt
template's bootstrap behaviour is covered separately in
``test_system_prompt_skills.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from crow_cli.agent.prompt import (
    AGENTS_FULL_LINES,
    _parse_frontmatter,
    build_agents_context,
    build_display_tree,
    get_skills,
    skill_roots,
)


def mk_skill(root: Path, name: str, content: str | None = None) -> Path:
    """Create ``root/name/SKILL.md`` with valid frontmatter unless overridden."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    text = content or f"---\nname: {name}\ndescription: the {name} skill\n---\nbody\n"
    (skill_dir / "SKILL.md").write_text(text)
    return skill_dir


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

    def test_returns_structured_skills(self, tmp_path):
        mk_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: first\n---\n")
        mk_skill(tmp_path, "beta", "---\nname: beta\ndescription: second\n---\n")
        skills = {s["name"]: s for s in get_skills(tmp_path)}
        assert set(skills) == {"alpha", "beta"}
        assert skills["alpha"]["description"] == "first"
        assert skills["alpha"]["path"].endswith("alpha/SKILL.md")

    def test_skips_invalid_entries(self, tmp_path):
        mk_skill(tmp_path, "good", "---\nname: good\ndescription: ok\n---\n")
        mk_skill(tmp_path, "no-name", "---\ndescription: missing name\n---\n")
        mk_skill(tmp_path, "no-fm", "# no frontmatter\n")
        mk_skill(tmp_path, "bad-yaml", '---\nname: "unclosed\n---\n')
        (tmp_path / "stray-file").write_text("not a skill dir")
        assert {s["name"] for s in get_skills(tmp_path)} == {"good"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert get_skills(tmp_path / "does-not-exist") == []


class TestSkillRoots:
    """Project skills come from hidden dirs between cwd and the git root; the
    user-level dir is scanned last so a project skill can shadow it."""

    def test_finds_hidden_dir_skills(self, tmp_path):
        project = tmp_path / "project"
        (project / ".agents" / "skills").mkdir(parents=True)
        roots = skill_roots(str(project), str(tmp_path / "user-skills"))
        assert project / ".agents" / "skills" in roots

    def test_scans_every_hidden_dir(self, tmp_path):
        project = tmp_path / "project"
        for hidden in (".agents", ".team"):
            (project / hidden / "skills").mkdir(parents=True)
        roots = skill_roots(str(project), str(tmp_path / "user-skills"))
        assert {r.parent.name for r in roots} >= {".agents", ".team"}

    def test_skips_machine_dirs_and_plain_dirs(self, tmp_path):
        project = tmp_path / "project"
        (project / ".git" / "skills").mkdir(parents=True)
        (project / "src" / "skills").mkdir(parents=True)
        roots = skill_roots(str(project), str(tmp_path / "user-skills"))
        assert roots == []

    def test_walks_up_to_git_root(self, tmp_path):
        repo = tmp_path / "repo"
        pkg = repo / "packages" / "thing"
        (repo / ".git").mkdir(parents=True)
        (repo / ".agents" / "skills").mkdir(parents=True)
        (pkg / ".agents" / "skills").mkdir(parents=True)
        roots = skill_roots(str(pkg), str(tmp_path / "user-skills"))
        assert pkg / ".agents" / "skills" in roots
        assert repo / ".agents" / "skills" in roots
        # Nearest first: the package's own skills win over the repo's.
        assert roots.index(pkg / ".agents" / "skills") < roots.index(
            repo / ".agents" / "skills"
        )

    def test_stops_at_git_root(self, tmp_path):
        outside = tmp_path / ".agents" / "skills"
        outside.mkdir(parents=True)
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        assert outside not in skill_roots(str(repo), str(tmp_path / "user-skills"))

    def test_user_dir_is_last(self, tmp_path):
        project = tmp_path / "project"
        user = tmp_path / "user-skills"
        (project / ".agents" / "skills").mkdir(parents=True)
        user.mkdir()
        roots = skill_roots(str(project), str(user))
        assert roots[-1] == user

    def test_user_dir_not_duplicated_when_cwd_is_home(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".agents" / "skills").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        roots = skill_roots(str(home), str(home / ".agents" / "skills"))
        assert len(roots) == 1


class TestSkillPrecedence:
    """Same name in two roots: the earlier (more local) root wins."""

    def test_project_shadows_user(self, tmp_path):
        project = tmp_path / "project"
        user = tmp_path / "user-skills"
        mk_skill(project / ".agents" / "skills", "deploy", "---\nname: deploy\ndescription: project\n---\n")
        mk_skill(user, "deploy", "---\nname: deploy\ndescription: user\n---\n")
        skills = {s["name"]: s for s in get_skills(skill_roots(str(project), str(user)))}
        assert skills["deploy"]["description"] == "project"

    def test_nearer_root_wins(self, tmp_path):
        repo = tmp_path / "repo"
        pkg = repo / "packages" / "thing"
        (repo / ".git").mkdir(parents=True)
        mk_skill(repo / ".agents" / "skills", "build", "---\nname: build\ndescription: repo\n---\n")
        mk_skill(pkg / ".agents" / "skills", "build", "---\nname: build\ndescription: package\n---\n")
        skills = {s["name"]: s for s in get_skills(skill_roots(str(pkg), str(tmp_path / "none")))}
        assert skills["build"]["description"] == "package"

    def test_shadowed_skill_is_logged(self, tmp_path, caplog):
        project = tmp_path / "project"
        user = tmp_path / "user-skills"
        mk_skill(project / ".agents" / "skills", "deploy", "---\nname: deploy\ndescription: project\n---\n")
        mk_skill(user, "deploy", "---\nname: deploy\ndescription: user\n---\n")
        with caplog.at_level("WARNING"):
            get_skills(skill_roots(str(project), str(user)))
        assert "shadows" in caplog.text


class TestBuildAgentsContext:
    """Two files load in full; everything else is a location + preview catalog."""

    @pytest.fixture
    def home(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".agents").mkdir(parents=True)
        monkeypatch.setattr("crow_cli.agent.prompt.AGENTS_DIR", home / ".agents")
        return home

    def test_global_and_cwd_load_in_full(self, home):
        (home / ".agents" / "AGENTS.md").write_text("GLOBAL RULE\n")
        project = home / "repo"
        project.mkdir()
        (project / "AGENTS.md").write_text("PROJECT RULE\n")
        ctx = build_agents_context(str(project))
        contents = {e["content"] for e in ctx["full"]}
        assert contents == {"GLOBAL RULE", "PROJECT RULE"}
        assert ctx["catalog"] == []

    def test_ancestor_files_are_cataloged_with_preview(self, home):
        repo = home / "repo"
        pkg = repo / "packages" / "thing"
        pkg.mkdir(parents=True)
        (repo / ".git").mkdir()
        lines = [f"line {i}" for i in range(1, 31)]
        (repo / "AGENTS.md").write_text("\n".join(lines) + "\n")
        ctx = build_agents_context(str(pkg))
        assert len(ctx["full"]) == 0 or all(
            e["path"] != str(repo / "AGENTS.md") for e in ctx["full"]
        )
        entry = next(e for e in ctx["catalog"] if e["path"] == str(repo / "AGENTS.md"))
        assert entry["preview"].splitlines() == lines[:5]

    def test_hidden_dir_rule_files_are_cataloged(self, home):
        project = home / "repo"
        (project / ".agents").mkdir(parents=True)
        (project / "AGENTS.md").write_text("cwd rule\n")
        (project / ".agents" / "AGENTS.md").write_text("hidden rule line 1\nline 2\n")
        ctx = build_agents_context(str(project))
        entry = next(e for e in ctx["catalog"] if ".agents" in e["path"])
        assert entry["preview"].startswith("hidden rule line 1")

    def test_oversized_file_is_demoted_not_truncated(self, home):
        project = home / "repo"
        project.mkdir()
        long = "\n".join(f"rule {i}" for i in range(1, AGENTS_FULL_LINES + 40))
        (project / "AGENTS.md").write_text(long + "\n")
        ctx = build_agents_context(str(project))
        assert ctx["full"] == []
        entry = ctx["catalog"][0]
        assert entry["path"] == str(project / "AGENTS.md")
        # The catalog entry is a preview; the full text is not in the prompt.
        assert "rule 250" not in entry["preview"]

    def test_no_files_reports_none_found(self, home):
        project = home / "repo"
        project.mkdir()
        ctx = build_agents_context(str(project))
        assert ctx["catalog"] == []
        assert ctx["full"][0]["content"] == "No AGENTS.md found"

    def test_global_file_counted_once_when_cwd_is_home(self, home):
        (home / ".agents" / "AGENTS.md").write_text("GLOBAL RULE\n")
        ctx = build_agents_context(str(home))
        assert len(ctx["full"]) == 1


class TestBuildDisplayTree:
    """The system prompt shows exactly one tree, rooted at cwd — never the
    shared ~/.agents workspaces, and no $HOME special case."""

    def test_only_cwd_tree_is_rendered(self, tmp_path):
        cwd = tmp_path / "project"
        cwd.mkdir()
        (cwd / "cwd_marker.txt").write_text("cwd")
        (cwd / "src").mkdir()
        (cwd / "src" / "main.py").write_text("")

        # Workspace-style trees living OUTSIDE cwd must not leak into the
        # output (this is what the old notes+skills+cwd rendering did).
        for name, marker in (("notes", "notes_marker.md"), ("skills", "SKILL.md")):
            ws = tmp_path / name
            ws.mkdir()
            (ws / marker).write_text("shared workspace")

        tree = build_display_tree(str(cwd))
        assert "cwd_marker.txt" in tree
        assert "main.py" in tree
        assert "notes_marker.md" not in tree
        assert "SKILL.md" not in tree
        # One tree block only — the old implementation joined notes/skills/cwd
        # sections with blank lines.
        assert "\n\n" not in tree

    def test_cwd_equal_to_home_still_renders_cwd_tree(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        (home / "home_marker.txt").write_text("home")
        monkeypatch.setenv("HOME", str(home))
        # Precondition: cwd really is $HOME, the case the old code skipped.
        assert os.path.realpath(str(home)) == os.path.realpath(Path.home())

        tree = build_display_tree(str(home))
        assert "home_marker.txt" in tree

    def test_missing_cwd_returns_empty_string(self, tmp_path):
        assert build_display_tree(str(tmp_path / "does-not-exist")) == ""
