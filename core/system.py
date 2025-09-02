# System orchestrator
from core.syscall import SystemCall
from myscheduler import *
from device import Device
from process import Process
from event import Event, EventType
from scheduler import Scheduler

# while event_queue:
#     event = heappop(event_queue)
#     current_time = event.time
#     handle_event(event)

# ------------------------------- System -------------------------------
class System:
    def __init__(self, devices: List[Device], commands: dict, time_quantum: int):
        self.devices = {d.name: d for d in devices}
        self.commands = commands  # command_name -> list[SystemCall]
        self.time_quantum = time_quantum

        # DES structures
        self.current_time = 0
        self.event_queue: List[Event] = []
        self._event_counter = 0

        self.scheduler = Scheduler(time_quantum=time_quantum)
        self.process_table: dict[int, Process] = {}

        # data-bus state
        self.bus_busy = False
        self.bus_owner: Optional[Process] = None

        # Statistics
        self.cpu_busy_time = 0  # microseconds spent executing processes

    # ------------------ Event queue helpers ------------------
    def push_event(self, time: int, etype: EventType, process: Optional[Process]=None, payload: Any=None):
        self._event_counter += 1
        ev = Event(time=int(time), order=self._event_counter, type=etype, process=process, payload=payload)
        heapq.heappush(self.event_queue, ev)
        return ev

    def pop_event(self) -> Optional[Event]:
        if not self.event_queue:
            return None
        return heapq.heappop(self.event_queue)

    # ------------------ Process creation ------------------
    def create_process(self, command_name: str, parent: Optional[Process]=None) -> Process:
        syscalls = [SystemCall(s.when, s.name, s.args) for s in self.commands[command_name]]
        p = Process(command_name, syscalls, parent)
        self.process_table[p.pid] = p
        if parent:
            parent.children.append(p)
        return p

    # ------------------ Start simulation ------------------
    def start(self):
        # Start by launching the first command in file
        if not self.commands:
            print("No commands to run.")
            return
        first_cmd = next(iter(self.commands.keys()))
        proc = self.create_process(first_cmd)
        # Arrival at time 0
        self.push_event(0, EventType.PROCESS_ARRIVAL, process=proc)
        # Run the main DES loop
        self.run()

    # ------------------ Main DES loop ------------------
    def run(self):
        while self.event_queue:
            ev = self.pop_event()
            if ev is None:
                break
            # advance time
            self.current_time = ev.time
            # debug print (can comment out later)
            # print(f"[t={self.current_time}] Handling {ev}")
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
            }.get(ev.type, None)

            if handler:
                handler(ev)
            else:
                print(f"No handler for event type {ev.type}")

        # Simulation finished: report
        total_time = self.current_time
        cpu_util = int((self.cpu_busy_time / total_time) * 100) if total_time > 0 else 0
        print(f"measurements  {total_time}  {cpu_util}")

    # ------------------ Event Handlers ------------------
    def _handle_arrival(self, ev: Event):
        p = ev.process
        p.state = 'READY'
        self.scheduler.enqueue_ready(p)
        # try to dispatch immediately if CPU idle
        if self.scheduler.running is None:
            self._attempt_dispatch()

    def _attempt_dispatch(self):
        if self.scheduler.running is not None:
            return
        if not self.scheduler.has_ready():
            return
        next_proc = self.scheduler.pick_next()
        if next_proc is None:
            return
        # simulate context-switch in cost before process starts running
        dispatch_complete_time = self.current_time + CONTEXT_SWITCH_IN
        next_proc.state = 'READY'  # still until dispatch completes
        # schedule dispatch complete
        self.push_event(dispatch_complete_time, EventType.DISPATCH_COMPLETE, process=next_proc)
        # mark scheduler as having someone scheduled to run (prevent double dispatch)
        self.scheduler.running = next_proc

    def _handle_dispatch_complete(self, ev: Event):
        p = ev.process
        # Now process moves to RUNNING state and will execute until either:
        # - quantum expires
        # - it reaches its next syscall
        p.state = 'RUNNING'
        # compute how long until next syscall (in CPU-time)
        t_until_syscall = p.time_until_next_syscall()
        run_for = self.time_quantum
        if t_until_syscall is not None:
            run_for = min(run_for, t_until_syscall)
        # schedule a RUN_COMPLETE at current_time + run_for
        run_end_time = self.current_time + run_for
        # increase cpu busy time by run_for
        self.cpu_busy_time += run_for
        # advance logical CPU-time for process accordingly (we defer incremental until event)
        self.push_event(run_end_time, EventType.RUN_COMPLETE, process=p)

    def _handle_run_complete(self, ev: Event):
        p = ev.process
        # determine if we reached a syscall or quantum expired
        t_until_syscall = p.time_until_next_syscall()
        if t_until_syscall is None or t_until_syscall > 0:
            # quantum expired
            # advance process cpu_time_executed by quantum
            p.cpu_time_executed += self.time_quantum if (t_until_syscall is None or t_until_syscall > self.time_quantum) else self.time_quantum
            # moving Running->Ready takes CONTEXT_SWITCH_MOVES microseconds
            unblock_time = self.current_time + CONTEXT_SWITCH_MOVES
            # schedule Blocked->Ready? Actually Running->Ready
            # We'll set state to READY after the move completes
            p.state = 'RUNNING'  # still running until switch completes
            # Once switch completes, enqueue ready and attempt dispatch
            self.push_event(unblock_time, EventType.BLOCKED_TO_READY, process=p, payload={'reason':'quantum'})
        else:
            # t_until_syscall == 0 meaning we should invoke syscall now
            # schedule SYSCALL_INVOKED immediately (no extra CPU time), but moving to blocked (if syscall blocks) costs CONTEXT_SWITCH_MOVES later
            # Advance cpu_time_executed up to the syscall point
            advance_by = p.time_until_next_syscall() if p.time_until_next_syscall() is not None else 0
            p.cpu_time_executed += advance_by
            # schedule syscall invocation at current time
            self.push_event(self.current_time, EventType.SYSCALL_INVOKED, process=p)

        # CPU is free now (or will be after the context-switch completing for quantum). For simplicity, if quantum expired we let BLOCKED_TO_READY handler attempt dispatch. If syscall invoked, handler will manage.
        if ev.process == self.scheduler.running:
            # clear running if it is the same process (we will set again if still running)
            self.scheduler.running = None
        # attempt immediate dispatch if ready processes exist and CPU free
        self._attempt_dispatch()

    def _handle_syscall_invoked(self, ev: Event):
        p = ev.process
        sc = p.current_syscall()
        if sc is None:
            # nothing to do
            return
        name = sc.name
        args = sc.args
        # We only support spawn, read, write, sleep, wait, exit
        if name == 'spawn':
            # spawn <command>
            cmd = args[0]
            # Create child process immediately
            child = self.create_process(cmd, parent=p)
            # The child should arrive to ready queue (arrival event at current_time)
            self.push_event(self.current_time, EventType.PROCESS_ARRIVAL, process=child)
            p.advance_pc()
            # after syscall invocation, the running process continues unless syscall blocks (spawn doesn't block)
            # Nothing else to do here.
        elif name in ('read', 'write'):
            devname = args[0]
            size = int(args[1].rstrip('B'))
            device = self.devices[devname]
            # enqueue on device; process will become Blocked after Running->Blocked cost
            request_id = (p.pid << 16) | p.pc
            enqueue_time = self.current_time
            device.enqueue(enqueue_time, p, name, size, request_id)
            p.blocked_reason = ('io', device.name, name, size, request_id)
            p.advance_pc()
            # moving Running->Blocked costs CONTEXT_SWITCH_MOVES (10us)
            to_block_time = self.current_time + CONTEXT_SWITCH_MOVES
            self.push_event(to_block_time, EventType.BLOCKED_TO_READY, process=p, payload={'reason':'io_block'})
            # attempt to start a bus transfer if bus idle
            self._try_start_bus_transfer()
        elif name == 'sleep':
            # sleep <usecs>
            duration = int(args[0].rstrip('usecs'))
            p.blocked_reason = ('sleep', duration)
            p.advance_pc()
            # process moves to blocked after Running->Blocked cost
            to_block_time = self.current_time + CONTEXT_SWITCH_MOVES
            wake_time = to_block_time + duration
            # schedule when sleep completes -> then BLOCKED_TO_READY which itself has CONTEXT_SWITCH_MOVES to move to ready
            self.push_event(wake_time, EventType.SLEEP_COMPLETE, process=p)
        elif name == 'wait':
            # Block until all children exit
            if not p.children:
                # nothing to wait for
                p.advance_pc()
            else:
                p.waiting_for_children = True
                p.blocked_reason = ('wait', None)
                p.advance_pc()
                # Running->Blocked cost
                to_block_time = self.current_time + CONTEXT_SWITCH_MOVES
                self.push_event(to_block_time, EventType.BLOCKED_TO_READY, process=p, payload={'reason':'wait_block'})
        elif name == 'exit':
            # process will exit after Running->Exit cost? According to spec, exit is instantaneous
            p.advance_pc()
            # schedule immediate process exit
            self.push_event(self.current_time, EventType.PROCESS_EXIT, process=p)
        else:
            raise ValueError(f"Unknown syscall {name}")

    def _handle_blocked_to_ready(self, ev: Event):
        p = ev.process
        reason = ev.payload.get('reason') if ev.payload else None
        # Distinguish why the event was scheduled:
        # - quantum expired -> enqueue ready
        # - IO block transition (Running->Blocked completed) -> set state BLOCKED
        # - wait_block -> set BLOCKED
        # - BLOCKED->READY after IO complete or sleep complete -> enqueue ready
        if reason == 'quantum':
            # Running -> Ready completed
            p.state = 'READY'
            self.scheduler.enqueue_ready(p)
        elif reason == 'io_block':
            # Running->Blocked completed. Mark blocked and clear running slot
            p.state = 'BLOCKED'
            # remove p from running if it was
            if self.scheduler.running == p:
                self.scheduler.running = None
            # nothing else; actual IO completion scheduled by device
        elif reason == 'wait_block':
            p.state = 'BLOCKED'
            if self.scheduler.running == p:
                self.scheduler.running = None
        else:
            # Generic BLOCKED->READY transition (used by IO_COMPLETE and SLEEP_COMPLETE handlers by scheduling this)
            # payload may include {'from':'io'} etc
            p.state = 'READY'
            p.blocked_reason = None
            # mark children waiting flag cleared for safety
            p.waiting_for_children = False
            self.scheduler.enqueue_ready(p)
        # attempt to dispatch if CPU idle
        self._attempt_dispatch()

    def _handle_io_complete(self, ev: Event):
        # payload contains device and request_id and process
        device_name = ev.payload['device']
        request_id = ev.payload['request_id']
        device = self.devices[device_name]
        device.in_use = False
        # free bus as well
        self.bus_busy = False
        self.bus_owner = None
        # find the process - we have it as ev.process in most cases
        p = ev.process
        # schedule Blocked->Ready (cost CONTEXT_SWITCH_MOVES)
        ready_time = self.current_time + CONTEXT_SWITCH_MOVES
        self.push_event(ready_time, EventType.BLOCKED_TO_READY, process=p, payload={'from':'io'})
        # After freeing device and bus, try to start next bus transfer
        self._try_start_bus_transfer()

    def _handle_sleep_complete(self, ev: Event):
        p = ev.process
        # After sleep duration elapsed, it still needs Blocked->Ready cost
        ready_move_time = self.current_time + CONTEXT_SWITCH_MOVES
        self.push_event(ready_move_time, EventType.BLOCKED_TO_READY, process=p, payload={'from':'sleep'})

    def _handle_spawn(self, ev: Event):
        # Not used in this design (spawn handled inline)
        pass

    def _handle_wait_complete(self, ev: Event):
        p = ev.process
        # called when children all exited; schedule blocked->ready
        ready_time = self.current_time + CONTEXT_SWITCH_MOVES
        self.push_event(ready_time, EventType.BLOCKED_TO_READY, process=p, payload={'from':'wait'})

    def _handle_process_exit(self, ev: Event):
        p = ev.process
        p.state = 'EXIT'
        # if parent waiting, check
        if p.ppid and p.ppid in self.process_table:
            parent = self.process_table[p.ppid]
            # remove child reference (or mark status)
            # It's simpler to leave in list but check parent's children statuses
            if parent.waiting_for_children:
                # if all children exited, schedule wait complete
                if all((child.state == 'EXIT') for child in parent.children):
                    self.push_event(self.current_time, EventType.WAIT_COMPLETE, process=parent)
        # remove process from table
        # We won't delete entry immediately so that pid references remain valid in events
        # But mark as exited
        # If this process was running, clear CPU slot
        if self.scheduler.running == p:
            self.scheduler.running = None
        # Simulation ends when no non-exited processes remain AND no events left. The DES loop will finish accordingly.

    # ------------------ I/O & Bus arbitration ------------------
    def _try_start_bus_transfer(self):
        # If bus busy, nothing to do
        if self.bus_busy:
            return
        # collect candidate devices that have non-empty queues
        candidates = [d for d in self.devices.values() if d.queue]
        if not candidates:
            return
        # Choose device with highest read_speed that has waiting processes
        candidates.sort(key=lambda d: (-d.read_speed, min(enq for enq, *_ in d.queue)))
        # From highest-speed device, pick the process that's been waiting the longest
        for dev in candidates:
            # pick earliest enqueue_time entry
            dev.queue.sort(key=lambda e: e[0])
            enq_time, proc, op, size, request_id = dev.queue.pop(0)
            # start transfer
            dev.in_use = True
            self.bus_busy = True
            self.bus_owner = proc
            # compute transfer time in microseconds
            speed = dev.read_speed if op == 'read' else dev.write_speed
            transfer_secs = size / speed
            transfer_usecs = math.ceil(transfer_secs * 1_000_000)
            # bus acquire delay applies before first transfer
            start_time = self.current_time + BUS_ACQUIRE_DELAY
            complete_time = start_time + transfer_usecs
            payload = {'device': dev.name, 'request_id': request_id}
            # schedule IO_COMPLETE for when transfer finishes
            self.push_event(complete_time, EventType.IO_COMPLETE, process=proc, payload=payload)
            return
