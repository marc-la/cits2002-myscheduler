"""
myscheduler.py


Discrete-Event Simulation of a single-CPU multi-device scheduler.


This file contains the classes and a runnable skeleton implementing the
objects discussed:
- Event / EventType
- SystemCall
- Process
- Device
- Scheduler
- System (DES loop)
- Parsers for sysconfig and commands


Usage:
python myscheduler.py sysconfig.txt commands.txt


This is a comprehensive, well-documented skeleton that implements the
project semantics (context-switch costs, I/O bus arbitration, blocked
queues per device, time-quantum preemption, spawn/wait/sleep/exit
syscalls) using a DES approach.


Note: This file is intended as a clear and extensible implementation
rather than the most compact solution. It aims to be readable and easy
to modify for testing and extension.
"""


import re
import math
import heapq
import sys
import argparse
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import deque, defaultdict
from typing import List, Optional, Any, Tuple
from simio.parser import parse_sysconfig, parse_commands
from core.system import System


# ----------------------------- Constants -----------------------------
CONTEXT_SWITCH_IN = 5 # Ready -> Running (microseconds)
CONTEXT_SWITCH_MOVES = 10 # Running->Blocked, Running->Ready, Blocked->Ready
BUS_ACQUIRE_DELAY = 20 # time to first acquire data-bus (microseconds)


# ------------------------------- CLI ---------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='myscheduler (DES-based scheduler simulator)')
    parser.add_argument('sysconfig', help='Path to sysconfig file')
    parser.add_argument('commands', help='Path to commands file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging of DES events')
    args = parser.parse_args()

    sysconfig_path = args.sysconfig
    commands_path = args.commands
    devices, tq = parse_sysconfig(sysconfig_path)
    commands = parse_commands(commands_path)
    print(f"found {len(devices)} devices")
    print(f"time quantum is {tq}")
    print(f"found {len(commands)} commands")
    s = System(devices, commands, time_quantum=tq, verbose=args.verbose)
    s.start()
