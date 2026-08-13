# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

a = Analysis(
    ['src/crow_cli/cli/main.py'],
    pathex=[],
    binaries=[],
    datas=(
        copy_metadata('fastmcp')
      + copy_metadata('agent-client-protocol')
      + copy_metadata('typer')
      + copy_metadata('rich')
      + copy_metadata('openai')
      + copy_metadata('httpx')
      + copy_metadata('jinja2')
      + copy_metadata('pyyaml')
      + copy_metadata('coolname')
      + copy_metadata('directory-tree')
    ),
    hiddenimports=[
        'crow_cli',
        'crow_memory',
        'crow_cli.agent',
        'crow_cli.agent.main',
        'crow_cli.agent.mcp_client',
        'crow_cli.agent.react',
        'crow_cli.agent.llm',
        'crow_cli.agent.session',
        'crow_cli.agent.compact',
        'crow_cli.agent.slash',
        'crow_cli.agent.context',
        'crow_cli.agent.configure',
        'crow_cli.client',
        'crow_cli.client.main',
        'crow_cli.agent_runner',
        'typer',
        'rich',
        'acp',
        'fastmcp',
        'openai',
        'httpx',
        'jinja2',
        'yaml',
        'coolname',
        'coolname.data',
        'directory_tree',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='crow-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
