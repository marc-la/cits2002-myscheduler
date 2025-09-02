# Scheduler class
from core import process
from myscheduler import *
from core.process import Process

class Scheduler:
    def __init__(self, time_quantum: int):
        self.time_quantum = time_quantum
        self.ready_queue: deque[Process] = deque()
        self.running: Optional[Process] = None
        self.cpu_context_switching = False

    def enqueue_ready(self, process: Process):
        process.state = 'READY'
        self.ready_queue.append(process)

    def has_ready(self) -> bool:
        return bool(self.ready_queue)

    def pick_next(self) -> Optional[Process]:
        if self.ready_queue:
            return self.ready_queue.popleft()
        return None