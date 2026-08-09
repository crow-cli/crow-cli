# Python REPL Integration

## Overview

Crow agents reason primarily in Python and have access to an actual Python REPL environment. This provides:

- **Jupyter-like experience**: Execute code interactively with persistent state
- **Shell replacement**: `!command` syntax for bash commands from Python
- **Full environment**: Connected to uv `.venv` with package management
- **Cell-based execution**: Like Jupyter but for LLM conversations

## Architecture

```
┌─────────────────────────────────────┐
│         Agent (GLM-4.7)            │
│  - Reasoning in Python              │
│  - Code generation                 │
└──────────┬──────────────────────────┘
           │
           │ Tool calls
           ▼
┌─────────────────────────────────────┐
│      MCP: Python REPL Server       │
│  - Execution context               │
│  - Output capture                  │
│  - Error handling                  │
└──────────┬──────────────────────────┘
           │
           │ Python code
           ▼
┌─────────────────────────────────────┐
│   Jupyter Kernel Gateway           │
│  - Persistent Python process        │
│  - Variable persistence             │
│  - Package management              │
└──────────┬──────────────────────────┘
           │
           │ uv .venv
           │ pip install
           ▼
┌─────────────────────────────────────┐
│      Python Environment             │
│  - Packages                       │
│  - Variables                      │
│  - Imports                        │
└─────────────────────────────────────┘
```

## Approach 1: Jupyter Kernel Gateway

The cleanest approach is to use Jupyter's kernel gateway.

### Setup

```bash
# Install Jupyter dependencies
uv pip install jupyter kernel_gateway ipython ipykernel

# Create a kernel for Crow
python -m ipykernel install --user --name=crow --display-name="Crow Agent"
```

### MCP Server for Jupyter Kernel

```python
import asyncio
from jupyter_client import KernelClient, kernelspec
from jupyter_client.kernelspec import KernelSpecManager
from typing import Optional
import json

class JupyterKernelMCP:
    """MCP server that connects to a Jupyter kernel"""
    
    def __init__(self, kernel_name: str = "crow"):
        self.kernel_name = kernel_name
        self.kernel_id: Optional[str] = None
        self.client: Optional[KernelClient] = None
        self._execution_count = 0
    
    async def connect(self):
        """Connect to Jupyter kernel"""
        import jupyter_client as jclient
        
        # Launch kernel
        km = jclient.KernelManager(kernel_name=self.kernel_name)
        km.start_kernel()
        
        # Get client
        self.client = km.client()
        self.kernel_id = km.kernel_id
        
        # Wait for kernel to be ready
        self.client.wait_for_ready(timeout=10)
        print(f"Connected to Jupyter kernel: {self.kernel_id}")
    
    async def execute_cell(
        self,
        code: str,
        timeout: int = 30
    ) -> dict:
        """
        Execute a code cell and return result
        
        Returns:
            dict with 'output', 'error', 'execution_count'
        """
        if not self.client:
            await self.connect()
        
        self._execution_count += 1
        
        # Send execute request
        self.client.execute(code, silent=False, store_history=True)
        
        # Gather outputs
        outputs = []
        error = None
        
        while True:
            try:
                msg = self.client.get_shell_msg(timeout=timeout)
                
                if msg['header']['msg_type'] == 'execute_reply':
                    # Check status
                    if msg['content']['status'] == 'error':
                        error = {
                            'ename': msg['content']['ename'],
                            'evalue': msg['content']['evalue'],
                            'traceback': msg['content']['traceback']
                        }
                    break
                
                # Collect IOPub messages (output, error, etc.)
                msg_type = self.client.get_iopub_msg(timeout=timeout)['header']['msg_type']
                
                if msg_type == 'stream':
                    data = self.client.get_iopub_msg(timeout=timeout)['content']
                    outputs.append({
                        'type': 'stream',
                        'name': data['name'],  # stdout or stderr
                        'text': data['text']
                    })
                
                elif msg_type == 'execute_result':
                    data = self.client.get_iopub_msg(timeout=timeout)['content']
                    outputs.append({
                        'type': 'result',
                        'data': data['data'],
                        'metadata': data.get('metadata', {})
                    })
                
                elif msg_type == 'error':
                    data = self.client.get_iopub_msg(timeout=timeout)['content']
                    error = {
                        'ename': data['ename'],
                        'evalue': data['evalue'],
                        'traceback': data['traceback']
                    }
                    break
                
                elif msg_type == 'display_data':
                    data = self.client.get_iopub_msg(timeout=timeout)['content']
                    outputs.append({
                        'type': 'display',
                        'data': data['data'],
                        'metadata': data.get('metadata', {})
                    })
            
            except Exception as e:
                error = {
                    'ename': type(e).__name__,
                    'evalue': str(e),
                    'traceback': []
                }
                break
        
        return {
            'output': outputs,
            'error': error,
            'execution_count': self._execution_count
        }
    
    async def get_variable(self, name: str) -> dict:
        """
        Get the value of a variable from the kernel
        
        Returns:
            dict with 'value' and 'type'
        """
        # Execute code to inspect variable
        inspect_code = f"""
import json
import builtins

# Try to serialize the variable
def serialize_var(obj):
    '''Safely serialize a variable'''
    try:
        return json.dumps({
            'type': type(obj).__name__,
            'value': str(obj),
            'repr': repr(obj)
        })
    except:
        return json.dumps({
            'type': type(obj).__name__,
            'value': '<unserializable>'
        })

try:
    result = serialize_var({name})
    print(repr(result))
except NameError:
    print(json.dumps({{'error': 'Variable not found'}}))
"""
        
        result = await self.execute_cell(inspect_code)
        
        if result['error']:
            return result['error']
        
        # Extract JSON from output
        if result['output']:
            for output in result['output']:
                if output['type'] == 'stream':
                    import json
                    return json.loads(output['text'].strip())
        
        return {'error': 'Could not retrieve variable'}
    
    async def install_package(self, package: str, version: Optional[str] = None) -> dict:
        """
        Install a package in the kernel's environment
        
        Uses uv if available, falls back to pip
        """
        version_spec = f"=={version}" if version else ""
        
        # Try uv first
        code = f"""
import subprocess
import sys

try:
    # Try uv
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "uv"],
        capture_output=True,
        timeout=30
    )
    
    if result.returncode == 0:
        # Use uv to install
        install_result = subprocess.run(
            ["uv", "pip", "install", "{package}{version_spec}"],
            capture_output=True,
            timeout=120
        )
        if install_result.returncode == 0:
            print("SUCCESS: Installed {package}{version_spec}")
            print(install_result.stdout.decode())
        else:
            print("ERROR: uv install failed")
            print(install_result.stderr.decode())
    else:
        raise Exception("uv not available")
        
except Exception:
    # Fallback to pip
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "{package}{version_spec}"],
        capture_output=True,
        timeout=120
    )
    if result.returncode == 0:
        print("SUCCESS: Installed {package}{version_spec}")
        print(result.stdout.decode())
    else:
        print("ERROR: pip install failed")
        print(result.stderr.decode())
"""
        
        return await self.execute_cell(code)
    
    async def restart_kernel(self):
        """Restart the kernel (clears all variables)"""
        if self.client:
            self.client.restart_kernel()
            self._execution_count = 0
            print("Kernel restarted")
    
    async def close(self):
        """Close connection to kernel"""
        if self.client:
            self.client.stop_channels()
```

### MCP Tool Registration

```python
from fastmcp import FastMCP

# Create MCP server
mcp_server = FastMCP("PythonREPL")

# Initialize kernel manager
kernel = JupyterKernelMCP()

@mcp_server.tool()
async def execute_python(code: str) -> str:
    """Execute Python code in a persistent REPL environment
    
    Args:
        code: Python code to execute
    
    Returns:
        Output from execution or error information
    """
    await kernel.connect()
    result = await kernel.execute_cell(code)
    
    if result['error']:
        return f"Error: {result['error']['ename']}: {result['error']['evalue']}\n" + \
               "\n".join(result['error']['traceback'])
    
    # Format outputs
    output_parts = []
    for output in result['output']:
        if output['type'] == 'stream':
            output_parts.append(f"[{output['name'].upper()}]:\n{output['text']}")
        elif output['type'] == 'result':
            # Try to pretty-print
            if 'text/plain' in output['data']:
                output_parts.append(f"RESULT:\n{output['data']['text/plain']}")
            else:
                output_parts.append(f"RESULT:\n{json.dumps(output['data'])}")
        elif output['type'] == 'display':
            output_parts.append(f"DISPLAY:\n{json.dumps(output['data'])}")
    
    return "\n\n".join(output_parts)

@mcp_server.tool()
async def get_variable(var_name: str) -> str:
    """Get the value and type of a variable
    
    Args:
        var_name: Name of the variable
    
    Returns:
        Variable information
    """
    await kernel.connect()
    result = await kernel.get_variable(var_name)
    return json.dumps(result, indent=2)

@mcp_server.tool()
async def install_package(package: str, version: str = None) -> str:
    """Install a Python package in the environment
    
    Args:
        package: Package name
        version: Optional version specifier
    
    Returns:
        Installation output
    """
    await kernel.connect()
    result = await kernel.install_package(package, version)
    
    if result['output']:
        return "\n".join(o['text'] for o in result['output'] if o['type'] == 'stream')
    elif result['error']:
        return str(result['error'])
    else:
        return "No output"

@mcp_server.tool()
async def python_repl_restart() -> str:
    """Restart the Python kernel (clears all variables)"""
    await kernel.restart_kernel()
    return "Kernel restarted - all variables cleared"

@mcp_server.resource("python_state")
async def get_python_state() -> str:
    """Get current Python environment state"""
    await kernel.connect()
    
    # Execute inspection code
    result = await kernel.execute_cell("""
import sys
import json

state = {
    'python_version': sys.version,
    'variables': list(globals().keys()),
    'modules': list(sys.modules.keys())
}

print(json.dumps(state, indent=2))
""")
    
    if result['output']:
        return result['output'][0]['text']
    
    return "{}"
```

## Approach 2: IPython Kernel Direct

Alternative approach using IPython directly (lighter weight):

```python
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from IPython.core.interactiveshell import InteractiveShell
from io import StringIO
import contextlib
import json

class IPythonREPL:
    """Direct IPython kernel without Jupyter"""
    
    def __init__(self):
        self.shell = TerminalInteractiveShell.instance()
        self._outputs: list[str] = StringIO()
    
    async def execute(self, code: str) -> dict:
        """Execute Python code"""
        
        # Capture output
        self._outputs = StringIO()
        
        with contextlib.redirect_stdout(self._outputs):
            try:
                result = self.shell.run_cell(code, silent=False, store_history=True)
                
                success = result.success
                error = None
                
                if result.error_in_exec:
                    error = {
                        'ename': result.error_in_exec.__class__.__name__,
                        'evalue': str(result.error_in_exec),
                        'traceback': []
                    }
                    success = False
                
            except Exception as e:
                success = False
                error = {
                    'ename': type(e).__name__,
                    'evalue': str(e),
                    'traceback': []
                }
        
        return {
            'success': success,
            'output': self._outputs.getvalue(),
            'result': result.result if success else None,
            'error': error
        }
```

## Jupyter-Style Cell Magic

Implement Jupyter-like cell syntax:

```python
class JupyterStyleREPL(JupyterKernelMCP):
    """REPL that supports Jupyter-style cell magic"""
    
    async def execute_cell_with_magic(self, cell_content: str) -> dict:
        """
        Execute with support for Jupyter-style magic:
        
        %%bash  - Execute in bash
        %%cd <dir>  - Change directory
        %pip install <pkg>  - Install package
        !<cmd>  - Shell command
        """
        
        lines = cell_content.strip().split('\n')
        
        # Check for cell magic (%%)
        if lines[0].startswith('%%'):
            magic = lines[0][2:].strip()
            code = '\n'.join(lines[1:])
            
            if magic == 'bash':
                return await self._execute_bash(code)
            elif magic.startswith('cd'):
                return await self._change_directory(magic[2:].strip())
            else:
                return {'error': f'Unknown magic: {magic}'}
        
        # Check for line magic (%) or shell (!)
        if cell_content.startswith('%'):
            magic = cell_content[1:].strip()
            if magic.startswith('pip install'):
                pkg = magic[len('pip install'):]
                return await self.install_package(pkg.strip())
        
        if cell_content.startswith('!'):
            return await self._execute_bash(cell_content[1:].strip())
        
        # Regular Python code
        return await self.execute_cell(cell_content)
    
    async def _execute_bash(self, command: str) -> dict:
        """Execute bash command"""
        code = f"""
import subprocess
import json

try:
    result = subprocess.run(
        {command!r},
        shell=True,
        capture_output=True,
        text=True,
        timeout=60
    )
    
    print(json.dumps({{
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr
    }}))
except subprocess.TimeoutExpired:
    print(json.dumps({{'error': 'Command timed out'}}))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
"""
        return await self.execute_cell(code)
    
    async def _change_directory(self, directory: str) -> dict:
        """Change working directory"""
        code = f"""
import os
import json

try:
    os.chdir({directory!r})
    print(json.dumps({{'success': True, 'cwd': os.getcwd()}}))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
"""
        return await self.execute_cell(code)
```

## System Prompt Integration

```python
PYTHON_REPL_SYSTEM_PROMPT = """You have access to a Python REPL environment for executing code.

**REPL Capabilities:**
- Execute Python code with persistent state (variables persist across calls)
- Install packages using `install_package()` or `%pip install <package>`
- Run shell commands with `!` prefix or `%%bash` cell magic  
- Inspect variables with `get_variable()` 
- Clear all state with `python_repl_restart()`

**Jupyter-style syntax you can use:**

```
%%bash
pip install package_name

OR

!pip install package_name

OR

import package_name
```

**Best Practices:**
1. Test code in small chunks before running complex operations
2. Use try-except blocks to handle errors gracefully
3. Inspect variables during execution with `get_variable()`
4. Install packages explicitly with `install_package()`
5. After modifying files, test the changes immediately

**Example pattern:**
```python
# First, check if package is available
!python -c "import requests; print(requests.__version__)"

# If not available, install it
!pip install requests

# Then use it
import requests
response = requests.get('https://api.example.com')
print(response.status_code)
```

Treat this REPL like a Jupyter notebook - you can build up state incrementally and inspect your code as you go."""
```

## Bash vs REPL Decision

The agent can use either the bash tool or the Python REPL. Guidelines:

**Use Bash for:**
- File operations (`ls`, `cd`, `mv`, `cp`)
- System commands
- Git operations

**Use Python REPL for:**
- Code testing and debugging
- Data manipulation
- Python package installation
- Web scraping with Python libraries

**Hybrid pattern:**
```python
# Use bash to find files
!find . -name "*.py" -type f

# Then use Python REPL to process them
import pathlib
files = list(pathlib.Path('.').glob('**/*.py'))
print(len(files))
```

## Error Handling

```python
class REPLSafeExecutor:
    """Wrapper for safe execution with timeouts and limits"""
    
    async def execute_with_safety(self, code: str, timeout: int = 30) -> dict:
        """Execute with safety measures"""
        
        # Limit execution time
        try:
            result = await asyncio.wait_for(
                self.kernel.execute_cell(code),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return {
                'error': {
                    'ename': 'TimeoutError',
                    'evalue': f'Execution exceeded {timeout}s',
                    'traceback': []
                }
            }
        
        # Check for dangerous operations
        dangerous_keywords = ['__import__', 'eval(', 'exec(', 'compile(']
        if any(keyword in code for keyword in dangerous_keywords):
            # Add warning but still execute
            if result.get('output'):
                result['warning'] = 'Code contains potentially dangerous operations'
        
        return result
```

## Testing

```python
async def test_python_repl():
    """Test Python REPL functionality"""
    
    kernel = await JupyterKernelMCP()
    await kernel.connect()
    
    # Test basic execution
    result = await kernel.execute_cell("x = 5 + 3\nprint(f'Result: {{x}}')")
    assert result['error'] is None
    
    # Test variable persistence
    result = await kernel.execute_cell("print(x * 2)")
    assert "16" in result['output'][0]['text']
    
    # Test package installation
    result = await kernel.install_package("requests")
    assert "SUCCESS" in result['output'][0]['text']
    
    # Test variable inspection
    result = await kernel.get_variable("x")
    assert result['value'] == "8"
    assert result['type'] == "int"
```

## Benefits

1. **Persistent state**: Variables persist across tool calls
2. **Jupyter experience**: Familiar workflow for developers
3. **Package management**: Easy dependency installation
4. **Rich output**: Support for plots, images, HTML output
5. **Integration**: Works well with coding workflow

## References

- Jupyter Client: https://jupyter-client.readthedocs.io/
- IPython: https://ipython.readthedocs.io/
