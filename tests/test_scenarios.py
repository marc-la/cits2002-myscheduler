import os
import re
import subprocess
import sys
import pytest


def run_case(sysconfig, commands):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    sysconfig_path = os.path.join(repo_root, sysconfig)
    commands_path = os.path.join(repo_root, commands)
    result = subprocess.run(
        [sys.executable, os.path.join(repo_root, 'myscheduler.py'), sysconfig_path, commands_path],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )
    assert result.returncode == 0, f"Return code {result.returncode}, stderr: {result.stderr}"
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    assert lines, 'No output'
    last = lines[-1]
    m = re.match(r"^measurements\s+(\d+)\s+(\d+)$", last)
    assert m, f"Malformed measurements line: {last}\nFull output:\n{result.stdout}"
    return int(m.group(1)), int(m.group(2))


# Baselines captured empirically on this implementation; allow tolerances
@pytest.mark.parametrize(
    'sysconfig,commands,baseline_time,baseline_cpu,tol_time,tol_cpu',
    [
        ('examples/sysconfig_tiny_quantum.txt', 'examples/commands_cpu_bound.txt', 400000, 50, 1000, 5),
        ('examples/sysconfig_mixed_speeds.txt', 'examples/commands_io_heavy.txt', 23333549, 0, 5000, 2),
        ('examples/sysconfig_asymmetric_rw.txt', 'examples/commands_spawn_tree.txt', 505855, 1, 2000, 5),
    ('examples/sysconfig_large_quantum.txt', 'examples/commands_cpu_bound.txt', 100300, 99, 1000, 5),
    ('examples/sysconfig_mixed_speeds.txt', 'examples/commands_contention.txt', 2500370, 0, 20000, 10),
    ('examples/sysconfig_tiny_quantum.txt', 'examples/commands_sleep_edges.txt', 25500, 0, 2000, 5),
    ('examples/sysconfig.txt', 'examples/commands_exact_boundary.txt', 500369, 0, 5000, 5),
    ('examples/sysconfig.txt', 'examples/commands_wait_no_children.txt', 104, 67, 100, 10),
    ],
)
def test_scenarios(sysconfig, commands, baseline_time, baseline_cpu, tol_time, tol_cpu):
    time_us, cpu = run_case(sysconfig, commands)
    assert abs(time_us - baseline_time) <= tol_time, f"time {time_us} not within ±{tol_time} of {baseline_time}"
    assert abs(cpu - baseline_cpu) <= tol_cpu, f"cpu {cpu} not within ±{tol_cpu} of {baseline_cpu}"
