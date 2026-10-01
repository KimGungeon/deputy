import unittest

from validation.runner.control import Controller, Limits
from validation.runner.supervisor import Supervisor


class TestSupervisor(unittest.TestCase):
    def supervisor(self, observations, remaining, costs, restart=None):
        clock = iter(range(100, 100 + len(observations) + 10))
        sleeps = []
        index = {"n":0}
        def next_observation():
            value = observations[min(index["n"], len(observations) - 1)]
            index["n"] += 1
            return value
        def next_value(values):
            return lambda: values[min(index["n"] - 1, len(values) - 1)]
        return Supervisor(Controller(Limits(seconds=1000, cost_usd=20,
                                            per_member_restarts=2, total_restarts=3)),
                           ("alpha", "beta"), next_observation,
                           next_value(remaining), next_value(costs), restart=restart,
                           interval=60, clock=lambda: next(clock), sleeper=sleeps.append), sleeps

    def test_two_confirmed_empty_observations_complete_and_stop(self):
        stopped = []
        sup, sleeps = self.supervisor([[{"name":"deputy-alpha"},{"name":"deputy-beta"}]] * 2,
                                      [0,0], [1,2])
        sup.stop = lambda: stopped.append(True)
        result = sup.run()
        self.assertEqual(result["terminal"], "completed")
        self.assertEqual(result["cycles"], 2)
        self.assertEqual(sleeps, [60])
        self.assertEqual(stopped, [True])

    def test_missing_member_restart_is_bounded_before_dispatch(self):
        attempts = []
        sup, _ = self.supervisor([[{"name":"deputy-alpha"}], [{"name":"deputy-alpha"}]],
                                 [1,1], [1,2], restart=lambda member: attempts.append(member) or False)
        result = sup.run(max_cycles=2)
        self.assertEqual(attempts, ["beta", "beta"])
        self.assertEqual(result["restarts"], {"beta":2})
        self.assertIsNone(result["terminal"])

    def test_bad_observation_stops_without_restart(self):
        restarts, stopped = [], []
        sup, _ = self.supervisor([None], [0], [1], restart=lambda m: restarts.append(m))
        sup.stop = lambda: stopped.append(True)
        result = sup.run(max_cycles=1)
        self.assertEqual(result["terminal"], "observation_failed")
        self.assertEqual(restarts, [])
        self.assertEqual(stopped, [True])

    def test_budget_terminal_stops_before_any_restart(self):
        stopped = []
        sup, _ = self.supervisor([[{"name":"deputy-alpha"}]], [2], [20],
                                 restart=lambda m: self.fail("restart after budget"))
        sup.stop = lambda: stopped.append(True)
        self.assertEqual(sup.run(max_cycles=1)["terminal"], "budget_limit")
        self.assertEqual(stopped, [True])

    def test_non_monotonic_cost_is_observation_failure(self):
        sup, _ = self.supervisor([[{"name":"deputy-alpha"}]] * 2, [1,1], [2,1])
        result = sup.run(max_cycles=2)
        self.assertEqual(result["terminal"], "observation_failed")
