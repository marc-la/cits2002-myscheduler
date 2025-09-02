import os
import re
import subprocess
import sys


def test_cli_measurements_line():
    repo_root = os.path.dirname(os.path.dirname(__file__))
    sysconfig = os.path.join(repo_root, 'examples', 'sysconfig.txt')
    commands = os.path.join(repo_root, 'examples', 'commands.txt')

    result = subprocess.run(
        [sys.executable, os.path.join(repo_root, 'myscheduler.py'), sysconfig, commands],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )

    assert result.returncode == 0, f"Process exited with {result.returncode}, stderr: {result.stderr}"

    # Ensure the last non-empty line matches the expected format
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    assert lines, "No output produced"
    last = lines[-1]
    assert re.match(r"^measurements\s+\d+\s+\d+$", last), f"Unexpected last line: {last}\nFull output:\n{result.stdout}"
