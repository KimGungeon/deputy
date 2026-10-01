"""Bounded orchestration loop for a live validation run.

The supervisor is deliberately callback-based: session observation, GitHub
remaining-work counts, cost metering, and restart are injected adapters. A
missing observation is a failure, never zero work or zero cost.
"""
from dataclasses import dataclass, field
import time

from .control import Controller


@dataclass
class Supervisor:
    controller: Controller
    members: tuple
    observe: object
    remaining: object
    cost: object
    restart: object = None
    stop: object = None
    interval: float = 60
    clock: object = time.monotonic
    sleeper: object = time.sleep
    events: list = field(default_factory=list)

    def __post_init__(self):
        if self.interval <= 0:
            raise ValueError("supervisor interval must be positive")
        self.members = tuple(self.members)

    def step(self):
        """Take one serialized observation and make bounded restart decisions."""
        started = self.clock()
        try:
            sessions = self.observe()
            remaining = self.remaining()
            cost = self.cost()
            if not isinstance(sessions, list):
                raise ValueError("session observation must be a list")
            names = {row.get("name") for row in sessions if isinstance(row, dict)}
            missing = [m for m in self.members if f"deputy-{m}" not in names]
            decision = self.controller.observe(
                elapsed=started, cost_usd=cost, remaining=remaining, healthy=True)
        except Exception as exc:
            self.controller.observe(elapsed=started, cost_usd=0,
                                    remaining=-1, healthy=False)
            event = {"kind":"observation_failed","error":f"{type(exc).__name__}: {exc}"}
            self.events.append(event)
            if self.stop:
                self.stop()
            return event

        event = {"kind":"observation","elapsed":started,"remaining":remaining,
                 "cost_usd":cost,"decision":decision,"missing":missing}
        self.events.append(event)
        if decision == "continue" and self.restart:
            for member in missing:
                if not self.controller.reserve_restart(member):
                    break
                try:
                    result = self.restart(member)
                except Exception as exc:
                    result = False
                    self.events.append({"kind":"restart_failed","member":member,
                                        "error":f"{type(exc).__name__}: {exc}"})
                else:
                    self.events.append({"kind":"restart_attempt","member":member,
                                        "success":bool(result)})
        if decision in {"completed", "time_limit", "budget_limit", "restart_limit",
                        "observation_failed"} and self.stop:
            self.stop()
        return event

    def run(self, *, max_cycles=None):
        """Run until a terminal controller state or an explicit cycle bound."""
        cycles = 0
        while not self.controller.terminal:
            if max_cycles is not None and cycles >= max_cycles:
                break
            self.step()
            cycles += 1
            if not self.controller.terminal:
                self.sleeper(self.interval)
        return {"terminal":self.controller.terminal,"cycles":cycles,
                "events":list(self.events),"restarts":dict(self.controller.restarts)}
