class Device:
    def __init__(self, name, read_speed, write_speed):
        self.name = name
        self.read_speed = read_speed  # bytes/sec
        self.write_speed = write_speed
        # queue of (enqueue_time, process, op, size, request_id)
        self.queue = []
        self.in_use = False

    def enqueue(self, enqueue_time, process, op, size, request_id):
        self.queue.append((enqueue_time, process, op, size, request_id))

    def pop_oldest(self):
        if not self.queue:
            return None
        self.queue.sort(key=lambda e: e[0])
        return self.queue.pop(0)

    def __repr__(self):
        return f"Device({self.name}, r={self.read_speed}, w={self.write_speed}, queued={len(self.queue)})"
