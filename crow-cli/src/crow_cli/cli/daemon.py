"""Daemon lifecycle for crow's infrastructure services.

Two kinds of services, one interface:

- ``process``: detached spawn in its own process group, pidfile backend
  (same conventions as the rust CLI):
      pidfile: {config_dir}/run/<name>.pid
      log:     {config_dir}/logs/<name>.log   (rotates 5 MB x 4 generations)
  stop = SIGTERM, then SIGKILL after the stop timeout.

- ``docker``: container operated via the docker SDK; when the container
  doesn't exist yet it is created from its compose file
  (``docker compose -f <file> up -d <service>``) — compose stays the
  definition source, the SDK does start/stop/status. The id of a
  container we started is recorded in the same pidfile slot, so
  stop/restart can refuse containers started elsewhere (unmanaged).

The registry is config-driven, precedence built-ins < ``services:`` <
``daemons:``:

- ``services:`` in config.yaml declares how to run additional things
  (typically MCP servers) as daemons — each entry takes the DaemonSpec
  keys (command, args, env, health_url, tcp_port, ...). A service that
  shares its name with an ``mcpServers`` entry and declares no health
  check gets its tcp probe port from that entry's url.
- ``daemons:`` overrides any spec, built-in or service-derived, by name.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

DEFAULT_MEMORY_PORT = 27697
DEFAULT_MCP_PORT = 2770
DEFAULT_OLLAMA_PORT = 11392
DEFAULT_SEARXNG_PORT = 2946

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_GENERATIONS = 4


@dataclass
class DaemonSpec:
    name: str
    kind: str = "process"  # process | docker
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    health_url: str | None = None
    tcp_port: int | None = None
    container: str | None = None
    compose_file: str | None = None
    compose_service: str | None = None
    start_timeout: float = 30.0
    stop_timeout: float = 5.0


def worktree_root() -> Path:
    """The repo root this CLI was installed from (<root>/crow-cli/src/crow_cli/cli)."""
    return Path(__file__).resolve().parents[4]


def _config_yaml(config_dir: Path) -> dict[str, Any]:
    path = config_dir / "config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _port_from_url(url: str) -> int | None:
    """Extract the port from an http(s) URL, if it has one."""
    hostpart = url.split("//")[-1].split("/", 1)[0]
    if ":" in hostpart:
        try:
            return int(hostpart.rsplit(":", 1)[1])
        except ValueError:
            return None
    return None


def _port_from_mcp_servers(cfg: dict[str, Any]) -> int:
    """Pull the crow-mcp port out of the mcpServers URL if it's http."""
    for name, srv in (cfg.get("mcpServers") or {}).items():
        if not name.startswith("crow-mcp"):
            continue
        port = _port_from_url((srv or {}).get("url", ""))
        if port is not None:
            return port
    return DEFAULT_MCP_PORT


def _apply_service_specs(
    specs: dict[str, DaemonSpec], cfg: dict[str, Any]
) -> None:
    """Register daemons from the top-level `services:` block — declarations
    of how to run things (typically MCP servers) as services. Only declared
    keys are set, so a service shadowing a built-in name patches it rather
    than clobbering it. If a service shares its name with an mcpServers
    entry and declares no health check, the port of that entry's url becomes
    the tcp health probe."""
    for name, service in (cfg.get("services") or {}).items():
        if not isinstance(service, dict):
            continue
        spec = specs.get(name)
        if spec is None:
            spec = DaemonSpec(name=name)
            specs[name] = spec
        for k, v in service.items():
            if hasattr(spec, k):
                setattr(spec, k, v)
        if spec.health_url is None and spec.tcp_port is None:
            mcp_entry = (cfg.get("mcpServers") or {}).get(name) or {}
            spec.tcp_port = _port_from_url(mcp_entry.get("url", ""))


def default_registry(config_dir: Path) -> dict[str, DaemonSpec]:
    """Built-in service registry, patched by config.yaml's `daemons:`."""
    cfg = _config_yaml(config_dir)
    root = worktree_root()

    memory_port = int(cfg.get("memory_port") or DEFAULT_MEMORY_PORT)
    mcp_port = _port_from_mcp_servers(cfg)

    ollama_candidates = [
        root / "vendor" / "ollama" / "ollama",        # `daemon install ollama-mv` build output
        config_dir / "vendor" / "ollama" / "ollama",  # fresh-machine clone location
        Path.home() / "src/crow-team/ollama/ollama",  # legacy dev checkout
    ]
    ollama_bin = os.environ.get("OLLAMA_MV_BIN") or next(
        (str(c) for c in ollama_candidates if c.is_file()), str(ollama_candidates[-1])
    )
    memory_bin = (
        os.environ.get("CROW_MEMORY_BIN")
        or (
            str(root / "target" / "release" / "crow-memory")
            if (root / "target" / "release" / "crow-memory").exists()
            else (shutil.which("crow-memory") or "crow-memory")
        )
    )
    mcp_bin = shutil.which("crow-mcp-dev")
    if mcp_bin is None:
        # Dev layout: the sibling project's venv console script.
        sibling = root / "crow-mcp" / ".venv" / "bin" / "crow-mcp-dev"
        mcp_bin = str(sibling) if sibling.exists() else "crow-mcp-dev"

    searxng_port = DEFAULT_SEARXNG_PORT
    env_file = config_dir / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("SEARXNG_PORT="):
                searxng_port = int(line.split("=", 1)[1].strip())

    specs = {
        "crow-memory": DaemonSpec(
            name="crow-memory",
            command=memory_bin,
            # Honor THIS config dir, not the server's built-in default —
            # memory_path/memory_port/embedding all come from this file, and
            # the server loads {config_dir}/.env itself for ports/secrets.
            args=["--config", str(config_dir / "config.yaml")],
            health_url=f"http://127.0.0.1:{memory_port}/healthz",
        ),
        "crow-mcp": DaemonSpec(
            name="crow-mcp",
            command=mcp_bin,
            args=["--transport", "http", "--host", "127.0.0.1", "--port", str(mcp_port)],
            # Point the memory tools at THIS config's crow-memory, not the
            # compiled-in default (critique: memory_port was silently ignored).
            env={"CROW_MEMORY_URL": f"http://127.0.0.1:{memory_port}"},
            tcp_port=mcp_port,
        ),
        "ollama-mv": DaemonSpec(
            name="ollama-mv",
            command=ollama_bin,
            args=["serve"],
            env={
                "OLLAMA_HOST": f"127.0.0.1:{DEFAULT_OLLAMA_PORT}",
                "OLLAMA_MODELS": str(Path.home() / ".local/share/ollama-mv-models"),
            },
            health_url=f"http://127.0.0.1:{DEFAULT_OLLAMA_PORT}/api/version",
            start_timeout=60.0,
        ),
        "searxng": DaemonSpec(
            name="searxng",
            kind="docker",
            container="crow-searxng-1",
            compose_file=str(config_dir / "compose.yaml"),
            compose_service="searxng",
            health_url=f"http://127.0.0.1:{searxng_port}/",
        ),
    }

    # services: block (e.g. MCP servers run as daemons), then daemons:
    # overrides on top — daemons: always wins.
    _apply_service_specs(specs, cfg)

    for name, overrides in (cfg.get("daemons") or {}).items():
        spec = specs.get(name)
        if spec is None:
            spec = DaemonSpec(name=name)
            specs[name] = spec
        for k, v in (overrides or {}).items():
            if hasattr(spec, k):
                setattr(spec, k, v)
    return specs


# ------------------------------------------------------------------ state --


def pid_file(config_dir: Path, name: str) -> Path:
    return config_dir / "run" / f"{name}.pid"


def log_file(config_dir: Path, name: str) -> Path:
    return config_dir / "logs" / f"{name}.log"


def _rotate_log(base: Path) -> None:
    try:
        if base.stat().st_size <= LOG_MAX_BYTES:
            return
    except OSError:
        return
    oldest = Path(f"{base}.{LOG_GENERATIONS}")
    oldest.unlink(missing_ok=True)
    for i in range(LOG_GENERATIONS - 1, 0, -1):
        gen = Path(f"{base}.{i}")
        if gen.exists():
            gen.rename(Path(f"{base}.{i + 1}"))
    base.rename(Path(f"{base}.1"))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers kill(pid, 0) but is dead — an unreaped daemon
    # must not read as "running" (stop would SIGKILL-escalate for nothing).
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def _read_record(config_dir: Path, name: str) -> str | None:
    """Raw pidfile content: a pid for process daemons, a container id for docker."""
    try:
        return pid_file(config_dir, name).read_text().strip() or None
    except OSError:
        return None


def read_pid(config_dir: Path, name: str) -> int | None:
    try:
        return int(_read_record(config_dir, name))
    except (TypeError, ValueError):
        return None


def healthy(spec: DaemonSpec) -> bool:
    if spec.health_url:
        try:
            return httpx.get(spec.health_url, timeout=2.0).status_code < 500
        except httpx.HTTPError:
            return False
    if spec.tcp_port:
        try:
            with socket.create_connection(("127.0.0.1", spec.tcp_port), timeout=1.0):
                return True
        except OSError:
            return False
    return True


def _docker_container(spec: DaemonSpec):
    import docker

    client = docker.from_env()
    try:
        return client.containers.get(spec.container), client
    except docker.errors.NotFound:
        return None, client


def status(config_dir: Path, spec: DaemonSpec) -> dict[str, Any]:
    """Live status. `managed` means we hold the pidfile (process) or our
    recorded container id matches (docker); a service can be running
    unmanaged (started elsewhere) — health still reports."""
    st: dict[str, Any] = {
        "name": spec.name,
        "kind": spec.kind,
        "pid": None,
        "managed": False,
        "running": False,
        "healthy": False,
    }
    if spec.kind == "docker":
        try:
            container, _ = _docker_container(spec)
        except Exception as e:  # docker missing / daemon down
            st["detail"] = f"docker: {e}"
            return st
        if container is None:
            return st
        st["running"] = container.status == "running"
        st["managed"] = st["running"] and _read_record(config_dir, spec.name) == container.id
        st["detail"] = container.status if st["managed"] or not st["running"] else "unmanaged"
        st["healthy"] = st["running"] and healthy(spec)
        return st

    pid = read_pid(config_dir, spec.name)
    if pid is not None and _alive(pid):
        st.update(pid=pid, managed=True, running=True)
    st["healthy"] = healthy(spec)
    if not st["running"] and st["healthy"]:
        # Up but not ours — started by hand or another manager.
        st["running"] = True
        st["detail"] = "unmanaged"
    return st


def _wait_healthy(spec: DaemonSpec, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if healthy(spec):
            return True
        time.sleep(0.3)
    return False


# ------------------------------------------------------------- lifecycle --


def start(config_dir: Path, spec: DaemonSpec) -> str:
    st = status(config_dir, spec)
    if st["running"]:
        return f"{spec.name}: already running" + (
            "" if st["managed"] else " (unmanaged — not touching it)"
        )

    if spec.kind == "docker":
        container, client = _docker_container(spec)
        if container is not None:
            container.start()
        else:
            if not spec.compose_file or not Path(spec.compose_file).exists():
                return f"{spec.name}: no container and no compose file at {spec.compose_file}"
            subprocess.run(
                [
                    "docker", "compose", "-f", spec.compose_file,
                    "up", "-d", spec.compose_service or spec.name,
                ],
                check=True,
                capture_output=True,
            )
            container, _ = _docker_container(spec)
        if container is not None:
            # Record the container we started so stop/restart can tell it
            # apart from one started elsewhere (unmanaged).
            pf = pid_file(config_dir, spec.name)
            pf.parent.mkdir(parents=True, exist_ok=True)
            pf.write_text(container.id)
        if _wait_healthy(spec, spec.start_timeout):
            return f"{spec.name}: started"
        return f"{spec.name}: started but not healthy yet — check `docker logs {spec.container}`"

    if not spec.command:
        return f"{spec.name}: no command configured"
    exe = spec.command
    if not (Path(exe).is_file() or shutil.which(exe)):
        return f"{spec.name}: command not found: {exe}"

    _rotate_log(log_file(config_dir, spec.name))
    pid_file(config_dir, spec.name).parent.mkdir(parents=True, exist_ok=True)
    log_file(config_dir, spec.name).parent.mkdir(parents=True, exist_ok=True)
    with open(log_file(config_dir, spec.name), "ab") as logf:
        proc = subprocess.Popen(
            [exe, *spec.args],
            stdout=logf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, **spec.env},
        )
    pid_file(config_dir, spec.name).write_text(str(proc.pid))
    if _wait_healthy(spec, spec.start_timeout):
        return f"{spec.name}: started (pid {proc.pid})"
    return (
        f"{spec.name}: spawned (pid {proc.pid}) but not healthy after "
        f"{spec.start_timeout:.0f}s — see {log_file(config_dir, spec.name)}"
    )


def stop(config_dir: Path, spec: DaemonSpec) -> str:
    if spec.kind == "docker":
        container, _ = _docker_container(spec)
        if container is None:
            pid_file(config_dir, spec.name).unlink(missing_ok=True)
            return f"{spec.name}: not running"
        if container.status != "running":
            return f"{spec.name}: not running"
        if _read_record(config_dir, spec.name) != container.id:
            return (
                f"{spec.name}: running unmanaged — not stopping it "
                "(stop it yourself; `daemon start` won't touch it)"
            )
        container.stop(timeout=int(spec.stop_timeout))
        pid_file(config_dir, spec.name).unlink(missing_ok=True)
        return f"{spec.name}: stopped"

    pid = read_pid(config_dir, spec.name)
    if pid is None or not _alive(pid):
        # Not ours. If something is still serving, refuse — we don't kill
        # processes we didn't start.
        if healthy(spec):
            return f"{spec.name}: running unmanaged — not killing it (stop it yourself or `daemon start` won't touch it)"
        pid_file(config_dir, spec.name).unlink(missing_ok=True)
        return f"{spec.name}: not running"

    # Daemons spawn in their own session (start_new_session=True), so the
    # recorded pid is also the pgid — signal the whole group, or children
    # of wrappers like `npm exec -> sh -> node` survive as orphans still
    # holding the port.
    def _signal(sig: int) -> None:
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    _signal(signal.SIGTERM)
    deadline = time.time() + spec.stop_timeout
    while time.time() < deadline and _alive(pid):
        time.sleep(0.1)
    if _alive(pid):
        _signal(signal.SIGKILL)
        time.sleep(0.2)
    pid_file(config_dir, spec.name).unlink(missing_ok=True)
    return f"{spec.name}: stopped" + ("" if not _alive(pid) else " (SIGKILL)")


def _unmanaged(config_dir: Path, spec: DaemonSpec) -> bool:
    """Service is up but we didn't start it (or lost track of it)."""
    if spec.kind == "docker":
        try:
            container, _ = _docker_container(spec)
        except Exception:
            return False
        return (
            container is not None
            and container.status == "running"
            and _read_record(config_dir, spec.name) != container.id
        )
    pid = read_pid(config_dir, spec.name)
    return (pid is None or not _alive(pid)) and healthy(spec)


def restart(config_dir: Path, spec: DaemonSpec) -> str:
    if _unmanaged(config_dir, spec):
        return (
            f"{spec.name}: running unmanaged — restart skipped "
            "(stop it yourself, then `daemon start`)"
        )
    stopped = stop(config_dir, spec)
    started = start(config_dir, spec)
    return f"{stopped}; {started}"
