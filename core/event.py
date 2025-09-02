from enum import Enum

class EventType(Enum):
    PROCESS_START = 1
    PROCESS_EXIT = 2
    QUANTUM_EXPIRE = 3
    IO_REQUEST = 4
    IO_COMPLETE = 5
    SLEEP_COMPLETE = 6
    SPAWN = 7
    WAIT_COMPLETE = 8

class Event:
    def __init__(self, time, event_type, process, extra=None):
        self.time = time
        self.event_type = event_type
        self.process = process
        self.extra = extra  # e.g., device info, child process, syscall args
    def __lt__(self, other):
        return self.time < other.time
