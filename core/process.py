# Process class
from core.syscall import SystemCall
from myscheduler import *

class Process:
    _pid_counter = 1

    def __init__(self, command_name: str, syscalls: List[SystemCall], parent: Optional['Process']=None):
        self.pid = Process._pid_counter
        Process._pid_counter += 1
        self.ppid = parent.pid if parent else None
        self.command_name = command_name
        self.syscalls = sorted(syscalls, key=lambda s: s.when)
        self.pc = 0  # index into syscalls
        self.state = 'NEW'  # NEW, READY, RUNNING, BLOCKED, EXIT
        self.cpu_time_executed = 0  # how many microseconds of CPU this process has used
        self.children: List[Process] = []
        self.waiting_for_children = False
        self.blocked_reason = None

    def time_until_next_syscall(self) -> Optional[int]:
        if self.pc >= len(self.syscalls):
            return None
        next_when = self.syscalls[self.pc].when
        return max(0, next_when - self.cpu_time_executed)

    def current_syscall(self) -> Optional[SystemCall]:
        if self.pc < len(self.syscalls):
            return self.syscalls[self.pc]
        return None

    def advance_pc(self):
        self.pc += 1

    def __repr__(self):
        return f"Process(pid={self.pid}, cmd={self.command_name}, state={self.state}, cpu_exec={self.cpu_time_executed}, pc={self.pc})"
