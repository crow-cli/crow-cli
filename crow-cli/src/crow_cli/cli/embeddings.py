"""ollama-mv provisioning — build the multivector ollama fork from source,
pull the ColBERT embedding model, verify a real embed call.

Driven by `crow-cli-dev daemon install ollama-mv`: on a fresh machine the
forks are cloned into {config_dir}/vendor and built (Go + cmake, CPU-only);
this worktree ships them as submodules under vendor/, preferred when
present. The built binary is written into config.yaml's `daemons:` section
(the registry override). The "embeddings download" IS the first embed call —
ollama pulls the model on demand.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import yaml

SERVICE_NAME = "ollama-mv"
PORT = 11392
EMBED_MODEL = "hf.co/LiquidAI/LFM2.5-ColBERT-350M-GGUF:LFM2.5-ColBERT-350M-BF16.gguf"

OLLAMA_REPO = "https://github.com/crow-cli/ollama.git"
LLAMACPP_REPO = "https://github.com/crow-cli/llama.cpp.git"


class ProvisionError(RuntimeError):
    pass


def find_go() -> str:
    g = os.environ.get("GO")
    if g:
        return g
    local = Path.home() / ".local/go/bin/go"
    if local.exists():
        return str(local)
    if shutil.which("go") is not None:
        out = subprocess.run(["go", "version"], capture_output=True)
        if out.returncode == 0:
            return "go"
    raise ProvisionError(
        "no Go toolchain found — install Go (https://go.dev/dl/) or set GO=/path/to/go"
    )


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    desc = " ".join(str(c) for c in cmd)
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env)
    except OSError as e:
        raise ProvisionError(f"spawning: {desc}: {e}")
    if proc.returncode != 0:
        raise ProvisionError(f"command failed: {desc}")


def _read_pin(ollama: Path) -> str:
    pin_file = ollama / "LLAMA_CPP_VERSION"
    try:
        return pin_file.read_text().strip()
    except OSError as e:
        raise ProvisionError(f"reading {pin_file}: {e}")


def _check_pin(ollama: Path, llamcpp: Path) -> None:
    pinned = _read_pin(ollama)
    out = subprocess.run(
        ["git", "describe", "--tags", "--exact-match"],
        cwd=llamcpp,
        capture_output=True,
        text=True,
    )
    at = out.stdout.strip() if out.returncode == 0 else ""
    if at != pinned:
        raise ProvisionError(
            f"{llamcpp} is at '{at or 'unknown'}' but {ollama} pins '{pinned}':\n"
            f"  git -C {llamcpp} fetch --depth 1 origin tag {pinned} "
            f"&& git -C {llamcpp} checkout {pinned}"
        )


def _vendor_checkouts(config_dir: Path) -> tuple[Path, Path]:
    """(ollama, llama.cpp) checkouts to build against. Prefer this
    worktree's vendor/ submodules; clone the forks into config_dir/vendor
    on a fresh machine."""
    from crow_cli.cli.daemon import worktree_root

    wt = worktree_root() / "vendor"
    if (wt / "ollama" / ".git").exists() and (wt / "llama.cpp" / ".git").exists():
        return wt / "ollama", wt / "llama.cpp"

    vendor = config_dir / "vendor"
    ollama, llamcpp = vendor / "ollama", vendor / "llama.cpp"
    if not (ollama / ".git").exists():
        print(f"cloning {OLLAMA_REPO}")
        _run(["git", "clone", "--depth", "1", OLLAMA_REPO, str(ollama)])
    if not (llamcpp / ".git").exists():
        pinned = _read_pin(ollama)
        print(f"cloning {LLAMACPP_REPO} @ {pinned}")
        _run(
            ["git", "clone", "--depth", "1", "--branch", pinned, LLAMACPP_REPO, str(llamcpp)]
        )
    return ollama, llamcpp


def build_from_source(config_dir: Path) -> Path:
    go = find_go()
    ollama, llamcpp = _vendor_checkouts(config_dir)
    _check_pin(ollama, llamcpp)

    env = {**os.environ, "OLLAMA_LLAMA_CPP_SOURCE": str(llamcpp)}
    print("configuring cmake (CPU-only, offline llama.cpp)")
    _run(
        [
            "cmake", "-B", "build", "-S", ".",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DGO_EXECUTABLE={go}",
        ],
        cwd=ollama,
        env=env,
    )
    jobs = min(os.cpu_count() or 8, 8)
    print(f"building ollama-mv (--parallel {jobs}) — this takes a while")
    _run(["cmake", "--build", "build", "--parallel", str(jobs)], cwd=ollama, env=env)

    binary = ollama / "ollama"
    if not binary.exists():
        raise ProvisionError(f"build finished but {binary} is missing")
    print(f"built {binary}")
    return binary


def _repoint_text(text: str, name: str, new_command: str) -> str | None:
    """Rewritten yaml text with the entry's command: replaced, or None if
    no `name:` block with a command: line exists. Surgical — comments and
    ordering survive."""
    out: list[str] = []
    entry_indent: int | None = None
    replaced = False
    for line in text.splitlines():
        trimmed = line.lstrip()
        indent = len(line) - len(trimmed)
        if entry_indent is not None and trimmed and indent <= entry_indent:
            entry_indent = None  # dedented past the entry — block over
        if entry_indent is None and trimmed == f"{name}:":
            entry_indent = indent
            out.append(line)
            continue
        if entry_indent is not None and not replaced and trimmed.startswith("command:"):
            out.append(line[:indent] + f"command: {new_command}")
            replaced = True
            continue
        out.append(line)
    if not replaced:
        return None
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def repoint_command(config_dir: Path, name: str, new_command: str) -> None:
    """Point config.yaml's daemons.<name>.command at new_command. Surgical
    line edit when the entry exists (comments survive); yaml merge when it
    doesn't."""
    path = config_dir / "config.yaml"
    text = path.read_text() if path.exists() else ""
    rewritten = _repoint_text(text, name, new_command)
    if rewritten is not None:
        path.write_text(rewritten)
        return
    cfg = yaml.safe_load(text) or {}
    if "daemons" not in cfg:
        # No daemons section yet: append a block — the rest of the file
        # stays byte-exact (comments survive).
        sep = "" if not text or text.endswith("\n") else "\n"
        path.write_text(text + sep + f"daemons:\n  {name}:\n    command: {new_command}\n")
        return
    daemons = cfg.get("daemons") or {}
    entry = daemons.get(name) or {}
    entry["command"] = new_command
    daemons[name] = entry
    cfg["daemons"] = daemons
    path.write_text(
        yaml.dump(cfg, default_flow_style=False, sort_keys=False, allow_unicode=True)
    )


def provision(config_dir: Path) -> Path:
    """Ensure the ollama-mv binary is built and config.yaml points at it.
    Idempotent. Returns the usable binary path."""
    from crow_cli.cli.daemon import default_registry

    spec = default_registry(config_dir)[SERVICE_NAME]
    binary = Path(os.path.expanduser(spec.command))
    if binary.is_file():
        return binary  # built already (dev tree or prior run) — idempotent

    # Command path is dead (repo moved) or never built. Build and repoint
    # the registry override in config.yaml.
    built = build_from_source(config_dir)
    repoint_command(config_dir, SERVICE_NAME, str(built))
    print(f"repointed {SERVICE_NAME} to {built}")
    return built


def verify_embeddings(
    port: int = PORT,
    attempts: int = 24,
    client: httpx.Client | None = None,
) -> bool:
    """Pull (on first call) + verify the ColBERT model with a real embed.
    Generous per-call timeout, retries while the runner cold-loads / the
    model downloads."""
    url = f"http://127.0.0.1:{port}/api/embed"
    body = {"model": EMBED_MODEL, "input": "crow warmup", "colbert": True}
    own_client = client is None
    http = client or httpx.Client(timeout=120.0)
    try:
        for attempt in range(1, attempts + 1):
            try:
                r = http.post(url, json=body)
                if r.status_code < 300 and "embeddings" in r.text:
                    print(f"embeddings: OK (http://127.0.0.1:{port})")
                    return True
                print(f"embed attempt {attempt}: HTTP {r.status_code}")
            except httpx.HTTPError as e:
                print(f"embed attempt {attempt}: {e}")
            time.sleep(5)
    finally:
        if own_client:
            http.close()
    return False
