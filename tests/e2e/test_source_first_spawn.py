"""E2E: from `crow-cli init` to a talking agent.

The whole claim in one test:

  1. ``bootstrap`` really clones the repo and really runs ``uv sync``, leaving
     a runnable checkout at ``<config_dir>/src/crow-cli``.
  2. That checkout runs ITS OWN code, not the tree the test was launched from.
  3. Crow's own agent never reaches for the checkout implicitly — pointing at
     it is an ``agent_servers`` entry the user writes, so the test builds that
     entry's launch string explicitly (what `crow-cli init` writes for them).
  4. That exact string, handed to a shell the way the TUI hands it, produces a
     live ACP agent that completes an ``initialize`` handshake.

The "remote" is this repository at its current branch, so what gets cloned and
spawned is the code under test. Nothing is mocked and no LLM is called: the
handshake is the assertion surface, and it needs no provider.

Live: needs ``git`` and ``uv`` on PATH; skips otherwise.
"""

import asyncio
import subprocess
from pathlib import Path

import pytest

from acp import PROTOCOL_VERSION, connect_to_agent
from acp.schema import ClientCapabilities, Implementation

from crow_cli.cli import source
from crow_cli.client.subagent import HeadlessClient
from crow_cli.tui.agent_servers import crow_agent

pytestmark = pytest.mark.asyncio

REPO = Path(__file__).resolve().parents[2]
HANDSHAKE_TIMEOUT = 240


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"git {args}: {proc.stderr}"
    return proc.stdout.strip()


@pytest.fixture
def this_repo_as_the_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point init's remotes at this working tree's repository.

    A clone only carries COMMITTED work, so the branch is whatever is checked
    out; the site repo is a local stub because it is not what is under test.
    """
    if not (REPO / ".git").exists():
        pytest.skip(f"{REPO} is not a git checkout")
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], REPO)
    if branch == "HEAD":
        pytest.skip("detached HEAD — clone_or_update needs a branch to track")

    site = tmp_path / "remotes" / "crow-cli.github.io"
    site.mkdir(parents=True)
    # BRANCH is global to bootstrap, so the stub site repo carries it too
    _git(["init", "-b", branch], site)
    (site / "README.md").write_text("# the site\n")
    _git(["add", "-A"], site)
    _git(["commit", "-m", "init"], site)

    monkeypatch.setattr(source, "CROW_REPO", str(REPO))
    monkeypatch.setattr(source, "BRANCH", branch)
    monkeypatch.setattr(source, "SITE_REPO", str(site))
    return REPO


async def test_init_clone_spawn_handshake(
    tmp_path: Path, this_repo_as_the_remote: Path
) -> None:
    if not source.uv_available():
        pytest.skip("uv is not on PATH")

    config_dir = tmp_path / "crow"

    # 1. init's source step, for real
    report = source.bootstrap(config_dir)
    assert report["errors"] == [], report["errors"]
    checkout = source.global_checkout(config_dir)
    assert source.is_checkout(checkout)
    assert report["synced"] is True
    if not (checkout / "src" / "crow_cli" / "cli" / "source.py").is_file():
        pytest.skip(f"the checked-out branch predates the current layout ({checkout})")

    # 2. the checkout's venv runs the CHECKOUT's code, not this tree's
    probe = subprocess.run(
        [
            "uv", "--project", str(checkout), "run", "python", "-c",
            "import crow_cli, sys; print(crow_cli.__file__); print(sys.executable)",
        ],
        capture_output=True,
        text=True,
        timeout=HANDSHAKE_TIMEOUT,
    )
    assert probe.returncode == 0, probe.stderr
    module_file, executable = probe.stdout.strip().splitlines()[-2:]
    assert module_file.startswith(str(checkout)), module_file
    assert executable.startswith(str(checkout)), executable
    assert str(REPO) not in module_file

    # 3. crow's own agent does NOT reach for the checkout implicitly; the
    #    launch that reaches it is an agent_servers entry, written explicitly.
    agent = crow_agent(config_dir=str(config_dir))
    assert "uv" not in agent["run_command"]["*"]
    command = f"uv --project {checkout} run crow-cli acp --config-dir {config_dir}"

    # 4. and that string, handed to a shell, is a live ACP agent
    proc = await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_path),
        limit=10 * 1024 * 1024,
    )
    try:
        conn = connect_to_agent(
            HeadlessClient(),
            proc.stdin,
            proc.stdout,
            use_unstable_protocol=True,
        )
        response = await asyncio.wait_for(
            conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(terminal=False),
                client_info=Implementation(
                    name="source-first-e2e", title="Source First E2E", version="0.1.0"
                ),
            ),
            timeout=HANDSHAKE_TIMEOUT,
        )
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    assert response.protocol_version is not None
    assert response.agent_capabilities is not None
    assert response.agent_capabilities.prompt_capabilities is not None
