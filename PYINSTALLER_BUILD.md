# PyInstaller Binary Build Setup

## ✅ What's Been Created

### 1. GitHub Workflow: `.github/workflows/build-binaries.yml`

Builds crow-cli binaries for:
- **Linux x86_64** (ubuntu-22.04)
- **macOS x86_64** (macos-13)
- **macOS ARM64** (macos-latest - Apple Silicon)

**Trigger:** Push version tags (e.g., `v0.1.13`)

**Output:** Creates GitHub release with attached archives:
- `crow-cli-linux-x86_64.tar.gz`
- `crow-cli-darwin-x86_64.tar.gz`
- `crow-cli-darwin-aarch64.tar.gz`

### 2. PyInstaller Spec File: `crow-cli/crow-cli.spec`

Configured with:
- **Metadata copying** for all packages using `importlib.metadata` (fastmcp, agent-client-protocol, typer, rich, openai, etc.)
- **Hidden imports** for dynamic imports (coolname.data, etc.)
- **Data files** included (config.yaml, system_prompt.jinja2, settings.yml, etc.)
- **One-file executable** with UPX compression

### 3. Dependencies: `crow-cli/pyproject.toml`

Added `pyinstaller>=6.0.0` to dev dependency group

## 🧪 Local Testing

```bash
cd crow-cli
uv pip install pyinstaller
uv run pyinstaller crow-cli.spec --noconfirm
dist/crow-cli --help
```

## 🚀 Usage

### To trigger a build:

1. Commit and push the workflow:
```bash
git add .github/workflows/build-binaries.yml
git add crow-cli/crow-cli.spec
git add crow-cli/pyproject.toml
git commit -m "Add PyInstaller binary build workflow"
git push
```

2. Create a test tag:
```bash
git tag v0.1.13-test
git push origin v0.1.13-test
```

3. GitHub Actions will build all platforms and create a release

### To update the ACP Registry:

After binaries are built, update `crow-cli/agent.json`:

```json
{
  "distribution": {
    "uvx": {...},
    "binary": {
      "darwin-aarch64": {
        "archive": "https://github.com/crow-cli/crow-cli/releases/download/v0.1.13/crow-cli-darwin-aarch64.tar.gz",
        "cmd": "./crow-cli",
        "args": ["acp"]
      },
      "darwin-x86_64": {...},
      "linux-x86_64": {...}
    }
  }
}
```

Then submit PR to [agentclientprotocol/registry](https://github.com/agentclientprotocol/registry)

## ⚠️ Known Issues & Solutions

### Package Metadata Errors
If you see `importlib.metadata.PackageNotFoundError`, add the package to the `copy_metadata()` calls in the spec file:

```python
datas=[
    ...
] + copy_metadata('packagename')
```

### Missing Module Errors
If you see `ModuleNotFoundError` for submodules, add to `hiddenimports`:

```python
hiddenimports=[
    'packagename.submodule',
    ...
]
```

### Build Size
Current Linux build: ~80MB (compressed with UPX)

## 📝 Notes

- The spec file handles all metadata copying, so no command-line flags needed
- macOS builds use different runners for Intel (macos-13) vs Apple Silicon (macos-latest)
- Artifacts are retained for 30 days, but releases are permanent
