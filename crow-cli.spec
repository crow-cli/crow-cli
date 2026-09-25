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
      + copy_metadata('crow-cli')
    ),
    hiddenimports=[
        'crow_cli',
        'crow_cli.memory',
        'crow_cli.agent',
        'crow_cli.agent.main',
        'crow_cli.agent.mcp_client',
        'crow_cli.agent.react',
        'crow_cli.agent.llm',
        'crow_cli.agent.session',
        'crow_cli.agent.compact',
        'crow_cli.agent.prompt',
        'crow_cli.agent.slash',
        'crow_cli.agent.context',
        'crow_cli.config',
        'crow_cli.client',
        'crow_cli.client.main',
        'crow_cli.agent_runner',
        # Lazy (PEP 562) facades resolve through importlib at runtime —
        # invisible to static analysis, so pin them here.
        'crow_cli.mcp.server.app',
        'crow_cli.mcp.server.main',
        'crow_cli.mcp.memory.main',
        'crow_cli.mcp.editor.main',
        'crow_cli.mcp.read.main',
        'crow_cli.mcp.terminal',
        'crow_cli.mcp.web_fetch',
        'crow_cli.mcp.web_search',
        'crow_cli.mcp.write.main',
        # --- ACP v2 -------------------------------------------------------
        # `crow-cli acp2` reaches agent2 through a function-level import, and
        # agent2 reaches its own submodules normally, so modulegraph would
        # most likely find all of this on its own. Pinned anyway, for the
        # reason the v1 block above is: a frozen build fails at RUNTIME, in
        # front of a client that spawned it over stdio, and "probably
        # followed" is not worth an ImportError there.
        'crow_cli.agent2',
        'crow_cli.agent2.main',
        'crow_cli.agent2.agent',
        'crow_cli.agent2.compaction',
        'crow_cli.agent2.ctx',
        'crow_cli.agent2.deliveries',
        'crow_cli.agent2.driver',
        'crow_cli.agent2.emitter',
        'crow_cli.agent2.events',
        'crow_cli.agent2.llm',
        'crow_cli.agent2.react',
        'crow_cli.agent2.replay',
        'crow_cli.agent2.sessions',
        'crow_cli.agent2.tools',
        'crow_cli.agent2.watcher',
        'crow_cli.client2',
        'crow_cli.client2.subagent',
        'crow_cli.wake',
        'crow_cli.timers',
        'acp.experimental.v2',
        # mcp2's registry maps a tool name to the module whose IMPORT
        # registers it, and register_tools() does the importing by string —
        # invisible to static analysis, exactly like the PEP 562 facades.
        'crow_cli.mcp2',
        'crow_cli.mcp2.main',
        'crow_cli.mcp2.server',
        'crow_cli.mcp2.execute',
        'crow_cli.mcp2.execute.main',
        'crow_cli.mcp2.execute.kernel',
        # The _LAZY_V2 subtools, resolved through importlib by
        # crow_cli.tools.reload(v2=True) inside the kernel.
        'crow_cli.tools.task_tool',
        'crow_cli.tools.goal_tool',
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
