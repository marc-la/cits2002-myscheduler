from collections import deque


class Scheduler:
    def __init__(self, time_quantum):
        self.time_quantum = time_quantum
        self.ready_queue = deque()
        self.running = None
        self.cpu_context_switching = False

    def enqueue_ready(self, process):
        process.state = 'READY'
        self.ready_queue.append(process)

    def has_ready(self):
        return bool(self.ready_queue)

    def pick_next(self):
        if self.ready_queue:
            return self.ready_queue.popleft()
        return None