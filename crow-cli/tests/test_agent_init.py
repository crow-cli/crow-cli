import json
import select
import subprocess
import sys
import threading
import time

msg = (
    json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                    "_meta": {"terminal_output": True, "terminal-auth": True},
                },
                "clientInfo": {
                    "name": "zed",
                    "title": "Zed",
                    "version": "0.224.11+stable.175.e4cabf49a18ed03969d84ee15643e9ec81857e97",
                },
            },
        }
    )
    + "\n"
)

proc = subprocess.Popen(
    [
        "uv",
        "--project",
        "/Users/thomas.wood/src/nid/crow-cli",
        "run",
        "crow-cli",
        "acp",
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Write the message
proc.stdin.write(msg.encode())
proc.stdin.flush()

# Read response with timeout
import fcntl
import os

flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

time.sleep(2)  # Give it time to process

# Try to read whatever is available
try:
    data = proc.stdout.read()
    if data:
        print("STDOUT:", data.decode())
    else:
        print("STDOUT: (empty)")
except Exception as e:
    print(f"Read error: {e}")

# Read stderr too
try:
    flags = fcntl.fcntl(proc.stderr, fcntl.F_GETFL)
    fcntl.fcntl(proc.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    err = proc.stderr.read()
    if err:
        print("STDERR:", err.decode()[-1000:])
except:
    pass

# Close stdin to let it exit
proc.stdin.close()
proc.wait(timeout=5)
print("Return code:", proc.returncode)
