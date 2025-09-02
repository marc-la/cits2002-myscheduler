from dataclasses import dataclass
from typing import List

@dataclass
class SystemCall:
    when: int   # CPU-time offset (microseconds) at which the syscall occurs
    name: str   # spawn/read/write/sleep/wait/exit
    args: List[str]

    def __repr__(self):
        return f"Syscall({self.when}us {self.name} {self.args})"