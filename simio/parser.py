# Config + command file parser
import re
from typing import List, Tuple

from core.device import Device
from core.syscall import SystemCall


def parse_sysconfig(path: str) -> Tuple[List[Device], int]:
    devices: List[Device] = []
    time_quantum = 100
    with open(path, 'r') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = re.split(r'\s+', line)
            if parts[0] == 'device':
                # device name readspeed writespeed
                name = parts[1]
                rs = int(parts[2].rstrip('Bps'))
                ws = int(parts[3].rstrip('Bps'))
                devices.append(Device(name, rs, ws))
            elif parts[0] == 'timequantum':
                time_quantum = int(parts[1].rstrip('usec'))
    return devices, time_quantum


def parse_commands(path: str) -> dict:
    commands = {}
    current_cmd = None
    with open(path, 'r') as fh:
        for raw in fh:
            line = raw.rstrip('\n')
            if not line.strip() or line.strip().startswith('#'):
                continue
            if not line.startswith('\t') and not line.startswith(' '):
                # command header
                current_cmd = line.strip()
                commands[current_cmd] = []
            else:
                # syscall line: format: \t<time>usecs    syscall   args...
                parts = re.split(r'\s+', line.strip())
                when = int(parts[0].rstrip('usecs'))
                name = parts[1]
                args = parts[2:]
                commands[current_cmd].append(SystemCall(when, name, args))
    return commands
