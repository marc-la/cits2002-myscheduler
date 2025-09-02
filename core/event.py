from myscheduler import *
from process import Process

class EventType(Enum):
    PROCESS_ARRIVAL = auto()
    DISPATCH_COMPLETE = auto()
    RUN_COMPLETE = auto()        # quantum expire OR syscall boundary reached
    SYSCALL_INVOKED = auto()
    IO_COMPLETE = auto()
    SLEEP_COMPLETE = auto()
    BLOCKED_TO_READY = auto()
    PROCESS_EXIT = auto()
    SPAWN = auto()
    WAIT_COMPLETE = auto()

@dataclass(order=True)
class Event:
    time: int
    order: int = field(compare=False)
    type: EventType = field(compare=False)
    process: Optional['Process'] = field(compare=False, default=None)
    payload: Any = field(compare=False, default=None)

    def __repr__(self):
        return f"Event(time={self.time}, type={self.type}, pid={getattr(self.process,'pid',None)}, payload={self.payload})"
