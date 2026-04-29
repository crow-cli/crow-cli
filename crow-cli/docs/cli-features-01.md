# CLI Features — Bite-by-Bite Changelog

## Bite 1: `--config-dir` + `--yes` flags on `init`

**What:** Added `--config-dir` / `-d` (default: `~/.crow`) and `--yes` / `-y` (skip all prompts) to `crow-cli init`.

**Why:** Testability. Non-interactive setup. CI pipelines.

**How:**
- `crow_cli/cli/main.py`: Added two typer options to `run_init()` callback
- `crow_cli/cli/init_cmd.py`: Updated `run_init(config_dir, yes)` to accept both params
- `load_dotenv()` at top of `init_cmd.py` so `.env` in current directory auto-loads

**Priority chain (highest → lowest):**
1. `config.yaml` in `config_dir` (loaded if exists, merged)
2. `LLM_*_API_KEY` / `LLM_*_BASE_URL` env vars
3. `.env` in current directory
4. Interactive prompts (or `--yes` to skip)

**Env var shortcuts:**
- `LLM_<PROVIDER>_API_KEY` + `LLM_<PROVIDER>_BASE_URL` → auto-detects provider in `--yes` mode
- `YES_INSTALL_SEARXNG=1` → skip SearXNG prompt
- `SEARXNG_PORT=5000` → override port

**Tested:** ✅ `--yes` mode works end-to-end, Docker containers start, config files written correctly.

**Next bite:** Move defaults from `defaults.py` Python strings into `init_defaults.yaml`.

---

## Bite 2: Defaults from YAML, not Python strings

**Status:** Planned

**What:** Migrate `COMPOSE_YAML`, `CONFIG_YAML`, `LITELLM_CONFIG_YAML`, `DEFAULT_SEARXNG_SETTINGS` from Python strings in `defaults.py` → single YAML file `crow_cli/cli/init_defaults.yaml`.

**Why:** 
- PyInstaller bundling easier
- Users can customize defaults
- YAML → YAML, not Python string → YAML

**Next bite:** Move defaults from Python strings → YAML file.
