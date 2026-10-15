"""Backend-independent decisions. Never turn a missing observation into zero."""
from dataclasses import dataclass, field
import math


@dataclass
class Limits:
    seconds: float = 1800
    cost_usd: float | None = 20
    per_member_restarts: int = 2
    total_restarts: int = 4

    def __post_init__(self):
        if not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("Time limit must be finite and positive")
        if self.cost_usd is not None and (not math.isfinite(self.cost_usd) or self.cost_usd <= 0):
            raise ValueError("Cost limit must be finite and positive when enabled")
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
        cost_valid = (self.limits.cost_usd is None and cost_usd is None) or (
            isinstance(cost_usd, (int, float)) and math.isfinite(cost_usd)
            and cost_usd >= self.last_cost)
        valid = (healthy and isinstance(remaining, int) and not isinstance(remaining, bool)
                 and remaining >= 0 and cost_valid
                 and isinstance(elapsed, (int, float)) and math.isfinite(elapsed)
                 and elapsed > self.last_elapsed)
        if not valid:
            self.terminal = "observation_failed"
        elif elapsed >= self.limits.seconds:
            self.terminal = "time_limit"
        elif self.limits.cost_usd is not None and cost_usd >= self.limits.cost_usd:
            self.terminal = "budget_limit"
        else:
            self.last_elapsed = elapsed
            if cost_usd is not None:
                self.last_cost = cost_usd
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
