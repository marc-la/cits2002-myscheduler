from typing import Any, List, Optional
import heapq
import math

from core.syscall import SystemCall
from core.device import Device
from core.process import Process
from core.event import Event, EventType
from core.scheduler import Scheduler


# Constants
CONTEXT_SWITCH_IN = 5
CONTEXT_SWITCH_MOVES = 10
BUS_ACQUIRE_DELAY = 20


class System:
    def __init__(self, devices: List[Device], commands: dict, time_quantum: int, verbose: bool = False):
        self.devices = {d.name: d for d in devices}
        self.commands = commands
        self.time_quantum = time_quantum
        self.verbose = verbose

        # DES structures
        self.current_time = 0
        self.event_queue = []
        self._event_counter = 0

        self.scheduler = Scheduler(time_quantum=time_quantum)
        self.process_table = {}

        # data-bus state
        self.bus_busy = False
        self.bus_owner = None

        # stats
        self.cpu_busy_time = 0

    # event queue helpers
    def push_event(self, time: int, etype: EventType, process: Optional[Process] = None, payload: Any = None):
        self._event_counter += 1
        ev = Event(time=int(time), order=self._event_counter, type=etype, process=process, payload=payload)
        heapq.heappush(self.event_queue, ev)
        if self.verbose:
            pid = getattr(process, 'pid', None)
            print(f"[t={time}] enqueue {etype.name} pid={pid} payload={payload}")
        return ev

    def pop_event(self) -> Optional[Event]:
        if not self.event_queue:
            return None
        return heapq.heappop(self.event_queue)

    # process creation
    def create_process(self, command_name: str, parent: Optional[Process] = None) -> Process:
        syscalls = [SystemCall(s.when, s.name, s.args) for s in self.commands[command_name]]
        p = Process(command_name, syscalls, parent)
        self.process_table[p.pid] = p
        if parent:
            parent.children.append(p)
        return p

    # start
    def start(self):
        if not self.commands:
            print("No commands to run.")
            return
        # Prefer to start the 'shell' if present; otherwise start the first command
        entry = 'shell' if 'shell' in self.commands else next(iter(self.commands.keys()))
        proc = self.create_process(entry)
        self.push_event(0, EventType.PROCESS_ARRIVAL, process=proc)
        self.run()

    # main DES loop
    def run(self):
        while self.event_queue:
            ev = self.pop_event()
            if ev is None:
                break
            self.current_time = ev.time
            if self.verbose:
                pid = getattr(ev.process, 'pid', None)
                print(f"[t={self.current_time}] handle {ev.type.name} pid={pid} payload={ev.payload}")
            handler = {
                EventType.PROCESS_ARRIVAL: self._handle_arrival,
                EventType.DISPATCH_COMPLETE: self._handle_dispatch_complete,
                EventType.RUN_COMPLETE: self._handle_run_complete,
                EventType.SYSCALL_INVOKED: self._handle_syscall_invoked,
                EventType.IO_COMPLETE: self._handle_io_complete,
                EventType.SLEEP_COMPLETE: self._handle_sleep_complete,
                EventType.BLOCKED_TO_READY: self._handle_blocked_to_ready,
                EventType.PROCESS_EXIT: self._handle_process_exit,
                EventType.SPAWN: self._handle_spawn,
                EventType.WAIT_COMPLETE: self._handle_wait_complete,
                EventType.CPU_AVAILABLE: self._handle_cpu_available,
            }.get(ev.type)
            if handler:
                handler(ev)

        total_time = self.current_time
        cpu_util = int((self.cpu_busy_time / total_time) * 100) if total_time > 0 else 0
        print(f"measurements {total_time} {cpu_util}")

    # handlers
    def _handle_arrival(self, ev: Event):
        p = ev.process
        p.state = 'READY'
        self.scheduler.enqueue_ready(p)
        if self.verbose:
            print(f"  pid={p.pid} -> READY (arrival)")
        if self.scheduler.running is None:
            self._attempt_dispatch()

    def _attempt_dispatch(self):
        if self.scheduler.running is not None:
            return
        if not self.scheduler.has_ready():
            return
        next_proc = self.scheduler.pick_next()
        if not next_proc:
            return
        dispatch_complete_time = self.current_time + CONTEXT_SWITCH_IN
        next_proc.state = 'READY'
        self.push_event(dispatch_complete_time, EventType.DISPATCH_COMPLETE, process=next_proc)
        # CPU is busy performing the context switch-in
        self.cpu_busy_time += CONTEXT_SWITCH_IN
        if self.verbose:
            print(f"  dispatching pid={next_proc.pid} (ctx-in {CONTEXT_SWITCH_IN}us)")
        self.scheduler.running = next_proc

    def _handle_dispatch_complete(self, ev: Event):
        p = ev.process
        p.state = 'RUNNING'
        p.quantum_left = self.time_quantum
        if self.verbose:
            print(f"  pid={p.pid} -> RUNNING, quantum={p.quantum_left}")
        # determine slice
        t_until = p.time_until_next_syscall()
        run_for = self.time_quantum if t_until is None else min(self.time_quantum, t_until)
        run_end_time = self.current_time + run_for
        self.cpu_busy_time += run_for
        self.push_event(run_end_time, EventType.RUN_COMPLETE, process=p, payload={"ran_for": run_for})

    def _handle_run_complete(self, ev: Event):
        p = ev.process
        ran_for = ev.payload.get("ran_for", 0) if ev.payload else 0
        p.cpu_time_executed += ran_for
        p.quantum_left = max(0, p.quantum_left - ran_for)
        t_after = p.time_until_next_syscall()
        if t_after == 0:
            # syscall boundary
            if self.verbose:
                print(f"  pid={p.pid} reached syscall boundary at cpu={p.cpu_time_executed}")
            self.push_event(self.current_time, EventType.SYSCALL_INVOKED, process=p)
        else:
            # quantum expired
            unblock_time = self.current_time + CONTEXT_SWITCH_MOVES
            self.push_event(unblock_time, EventType.BLOCKED_TO_READY, process=p, payload={'reason': 'quantum'})
            if self.scheduler.running == p:
                self.scheduler.running = None
            # Do not dispatch immediately; wait until move completes at unblock_time

    def _schedule_continue_running(self, p: Process):
        if p.quantum_left <= 0:
            # time slice over, will be handled elsewhere
            return
        t_until = p.time_until_next_syscall()
        run_for = p.quantum_left if t_until is None else min(p.quantum_left, t_until)
        if run_for <= 0:
            return
        run_end_time = self.current_time + run_for
        self.cpu_busy_time += run_for
        self.push_event(run_end_time, EventType.RUN_COMPLETE, process=p, payload={"ran_for": run_for})

    def _handle_syscall_invoked(self, ev: Event):
        p = ev.process
        sc = p.current_syscall()
        if sc is None:
            return
        name = sc.name
        args = sc.args
        if name == 'spawn':
            cmd = args[0]
            child = self.create_process(cmd, parent=p)
            self.push_event(self.current_time, EventType.PROCESS_ARRIVAL, process=child)
            p.advance_pc()
            # continue running within remaining quantum
            self._schedule_continue_running(p)
        elif name in ('read', 'write'):
            devname = args[0]
            size = int(args[1].rstrip('B'))
            device = self.devices[devname]
            request_id = (p.pid << 16) | p.pc
            device.enqueue(self.current_time, p, name, size, request_id)
            p.blocked_reason = ('io', device.name, name, size, request_id)
            p.advance_pc()
            to_block_time = self.current_time + CONTEXT_SWITCH_MOVES
            self.push_event(to_block_time, EventType.BLOCKED_TO_READY, process=p, payload={'reason': 'io_block'})
            # CPU freed
            if self.scheduler.running == p:
                self.scheduler.running = None
            # Do not dispatch immediately; wait until move completes
            self._try_start_bus_transfer()
        elif name == 'sleep':
            duration = int(args[0].rstrip('usecs'))
            p.blocked_reason = ('sleep', duration)
            p.advance_pc()
            to_block_time = self.current_time + CONTEXT_SWITCH_MOVES
            wake_time = to_block_time + duration
            self.push_event(wake_time, EventType.SLEEP_COMPLETE, process=p)
            if self.scheduler.running == p:
                self.scheduler.running = None
            # Do not dispatch immediately; wait until move completes
        elif name == 'wait':
            if not p.children:
                p.advance_pc()
                self._schedule_continue_running(p)
            else:
                p.waiting_for_children = True
                p.blocked_reason = ('wait', None)
                p.advance_pc()
                to_block_time = self.current_time + CONTEXT_SWITCH_MOVES
                self.push_event(to_block_time, EventType.BLOCKED_TO_READY, process=p, payload={'reason': 'wait_block'})
                if self.scheduler.running == p:
                    self.scheduler.running = None
                # Do not dispatch immediately; wait until move completes
        elif name == 'exit':
            p.advance_pc()
            self.push_event(self.current_time, EventType.PROCESS_EXIT, process=p)
            if self.scheduler.running == p:
                self.scheduler.running = None
            # After exit, CPU can dispatch after move cost
            self.push_event(self.current_time + CONTEXT_SWITCH_MOVES, EventType.CPU_AVAILABLE)
        else:
            raise ValueError(f"Unknown syscall {name}")

    def _handle_blocked_to_ready(self, ev: Event):
        p = ev.process
        reason = ev.payload.get('reason') if ev.payload else None
        if reason == 'quantum':
            p.state = 'READY'
            self.scheduler.enqueue_ready(p)
            if self.verbose:
                print(f"  pid={p.pid} quantum expired -> READY")
        elif reason == 'io_block':
            p.state = 'BLOCKED'
            if self.verbose:
                print(f"  pid={p.pid} -> BLOCKED (I/O enqueued)")
        elif reason == 'wait_block':
            p.state = 'BLOCKED'
            if self.verbose:
                print(f"  pid={p.pid} -> BLOCKED (wait)")
        else:
            p.state = 'READY'
            p.blocked_reason = None
            p.waiting_for_children = False
            self.scheduler.enqueue_ready(p)
            if self.verbose:
                print(f"  pid={p.pid} unblocked -> READY")
        self._attempt_dispatch()

    def _handle_io_complete(self, ev: Event):
        device_name = ev.payload['device']
        device = self.devices[device_name]
        device.in_use = False
        self.bus_busy = False
        self.bus_owner = None
        p = ev.process
        # I/O completion makes the process ready immediately
        self.push_event(self.current_time, EventType.BLOCKED_TO_READY, process=p, payload={'from': 'io'})
        self._try_start_bus_transfer()

    def _handle_sleep_complete(self, ev: Event):
        p = ev.process
        # Sleep completion makes the process ready immediately
        self.push_event(self.current_time, EventType.BLOCKED_TO_READY, process=p, payload={'from': 'sleep'})

    def _handle_spawn(self, ev: Event):
        pass

    def _handle_wait_complete(self, ev: Event):
        p = ev.process
        # Wait completion makes the process ready immediately
        self.push_event(self.current_time, EventType.BLOCKED_TO_READY, process=p, payload={'from': 'wait'})

    def _handle_process_exit(self, ev: Event):
        p = ev.process
        p.state = 'EXIT'
        if p.ppid and p.ppid in self.process_table:
            parent = self.process_table[p.ppid]
            if parent.waiting_for_children:
                if all((child.state == 'EXIT') for child in parent.children):
                    self.push_event(self.current_time, EventType.WAIT_COMPLETE, process=parent)
        if self.scheduler.running == p:
            self.scheduler.running = None
        # After a process exits, if no other event re-triggers dispatch, ensure CPU dispatches
        self.push_event(self.current_time + CONTEXT_SWITCH_MOVES, EventType.CPU_AVAILABLE)

    def _handle_cpu_available(self, ev: Event):
        # A signal that the CPU can attempt to dispatch a new process now
        self._attempt_dispatch()

    # I/O and bus arbitration
    def _try_start_bus_transfer(self):
        if self.bus_busy:
            return
        candidates = [d for d in self.devices.values() if d.queue]
        if not candidates:
            return
        candidates.sort(key=lambda d: (-d.read_speed, min(enq for enq, *_ in d.queue)))
        for dev in candidates:
            dev.queue.sort(key=lambda e: e[0])
            enq_time, proc, op, size, request_id = dev.queue.pop(0)
            dev.in_use = True
            self.bus_busy = True
            self.bus_owner = proc
            speed = dev.read_speed if op == 'read' else dev.write_speed
            transfer_secs = size / speed
            transfer_usecs = math.ceil(transfer_secs * 1_000_000)
            start_time = self.current_time + BUS_ACQUIRE_DELAY
            complete_time = start_time + transfer_usecs
            payload = {'device': dev.name, 'request_id': request_id}
            self.push_event(complete_time, EventType.IO_COMPLETE, process=proc, payload=payload)
            if self.verbose:
                print(f"  BUS {dev.name} {op} pid={proc.pid} size={size}B speed={speed}Bps start@{start_time} done@{complete_time}")
            return
