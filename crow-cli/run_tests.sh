#!/home/thomas/src/backup/nid-backup/crow-cli/.venv/bin/python
# Run tests using the project's virtual environment
import sys
import subprocess

sys.exit(subprocess.run(["/home/thomas/src/backup/nid-backup/crow-cli/.venv/bin/python", "-m", "pytest"] + sys.argv[1:]).returncode)
