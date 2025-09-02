# Device class
from myscheduler import *
from core.process import Process

class Device:
    def __init__(self, name: str, read_speed: int, write_speed: int):
        self.name = name
        self.read_speed = read_speed  # bytes/sec
        self.write_speed = write_speed
        # queue of (enqueue_time, process, op, size, request_id)
        self.queue: List[Tuple[int, Process, str, int, int]] = []
        self.in_use: bool = False

    def enqueue(self, enqueue_time: int, process: Process, op: str, size: int, request_id: int):
        self.queue.append((enqueue_time, process, op, size, request_id))

    def pop_oldest(self):
        if not self.queue:
            return None
        # oldest by enqueue_time
        self.queue.sort(key=lambda e: e[0])
        return self.queue.pop(0)

    def __repr__(self):
        return f"Device({self.name}, r={self.read_speed}, w={self.write_speed}, queued={len(self.queue)})"
