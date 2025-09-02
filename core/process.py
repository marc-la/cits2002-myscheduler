from typing import Optional, List
from core.syscall import SystemCall


class Process:
    _pid_counter = 1

    def __init__(self, command_name: str, syscalls: List[SystemCall], parent: Optional['Process'] = None):
        self.pid = Process._pid_counter
        Process._pid_counter += 1
        self.ppid = parent.pid if parent else None
        self.command_name = command_name
        self.syscalls = sorted(syscalls, key=lambda s: s.when)
        self.pc = 0
        self.state = 'NEW'
        self.cpu_time_executed = 0
        self.children: List['Process'] = []
        self.waiting_for_children = False
        self.blocked_reason: Optional[str] = None
        self.quantum_left = 0
        self.has_acquired_bus = False

    def time_until_next_syscall(self) -> Optional[int]:
        if self.pc >= len(self.syscalls):
            return None
        next_when = self.syscalls[self.pc].when
        return max(0, next_when - self.cpu_time_executed)

    def current_syscall(self) -> Optional[SystemCall]:
        if self.pc < len(self.syscalls):
            return self.syscalls[self.pc]
        return None

    def advance_pc(self) -> None:
        self.pc += 1

    def __repr__(self) -> str:
        return f"Process(pid={self.pid}, cmd={self.command_name}, state={self.state}, cpu_exec={self.cpu_time_executed}, pc={self.pc})"
