"""Backend-independent decisions. Never turn a missing observation into zero."""
from dataclasses import dataclass, field
import math


@dataclass
class Limits:
    seconds: float = 1800
    cost_usd: float = 20
    per_member_restarts: int = 2
    total_restarts: int = 4

    def __post_init__(self):
        if not all(math.isfinite(n) and n > 0 for n in (self.seconds, self.cost_usd)):
            raise ValueError("Time and cost limits must be finite and positive")
        if self.per_member_restarts < 0 or self.total_restarts < 0:
            raise ValueError("Restart limits cannot be negative")


@dataclass
class Controller:
    limits: Limits
    restarts: dict = field(default_factory=dict)
    completed_observations: int = 0
    terminal: str | None = None
    last_elapsed: float = -1
    last_cost: float = 0

    def observe(self, *, elapsed, cost_usd, remaining, healthy=True):
        if self.terminal:
            return self.terminal
        valid = (healthy and isinstance(remaining, int) and not isinstance(remaining, bool)
                 and remaining >= 0 and isinstance(cost_usd, (int, float))
                 and math.isfinite(cost_usd) and cost_usd >= self.last_cost
                 and isinstance(elapsed, (int, float)) and math.isfinite(elapsed)
                 and elapsed > self.last_elapsed)
        if not valid:
            self.terminal = "observation_failed"
        elif elapsed >= self.limits.seconds:
            self.terminal = "time_limit"
        elif cost_usd >= self.limits.cost_usd:
            self.terminal = "budget_limit"
        else:
            self.last_elapsed, self.last_cost = elapsed, cost_usd
            self.completed_observations = self.completed_observations + 1 if remaining == 0 else 0
            if self.completed_observations >= 2:
                self.terminal = "completed"
        return self.terminal or ("confirm_completion" if remaining == 0 else "continue")

    def reserve_restart(self, member):
        """Count attempts before dispatch, including launch failures."""
        if self.terminal or self.completed_observations:
            return False
        if (self.restarts.get(member, 0) >= self.limits.per_member_restarts or
                sum(self.restarts.values()) >= self.limits.total_restarts):
            self.terminal = "restart_limit"
            return False
        self.restarts[member] = self.restarts.get(member, 0) + 1
        return True
