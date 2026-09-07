"""decide_action() 은 README 의 우선순위/행동 표를 그대로 구현한 함수다.
'deputy <번호>' 가 이슈 상태별로 옳은 행동을 고르는지 각 분기를 확인한다.

주의: 함수 docstring 은 "네트워크를 타지 않는 순수 함수"라고 주장하지만
deputy:epic 분기는 내부적으로 open_children() -> issue() 를 호출해 실제로는
네트워크를 탄다. 그 분기의 테스트는 issue() 를 모킹해서 격리한다.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deputy_module import load

deputy = load()
decide_action = deputy.decide_action
COORDINATOR = deputy.COORDINATOR
BUILDER = deputy.BUILDER


def iso(seconds_ago=0):
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return dt.isoformat().replace("+00:00", "Z")


def mark(kind, by, rev=None, verdict=None, parent=None, owner=None, after=None):
    parts = [f"kind={kind}", f"by={by}"]
    if parent is not None:
        parts.append(f"parent={parent}")
    if owner is not None:
        parts.append(f"owner={owner}")
    if after is not None:
        parts.append(f"after={after}")
    if rev is not None:
        parts.append(f"rev={rev}")
    if verdict is not None:
        parts.append(f"verdict={verdict}")
    return "<!-- deputy v1 " + " ".join(parts) + " -->"


def comment(kind, by, seconds_ago=0, rev=None, verdict=None):
    return {"body": mark(kind, by, rev=rev, verdict=verdict) + "\n(테스트)",
            "createdAt": iso(seconds_ago)}


def make_cfg(builders, coordinators=()):
    members = [{"name": b} for b in builders]
    members += [{"name": c, "role": COORDINATOR} for c in coordinators]
    return {"members": members, "review_timeout_minutes": 45, "max_revisions": 2}


def make_issue(number=1, state="OPEN", body="", comments=(), labels=()):
    return {"number": number, "state": state, "body": body,
            "comments": list(comments), "labels": [{"name": l} for l in labels]}


class TestClosed(unittest.TestCase):
    def test_closed_issue_short_circuits(self):
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a",
                                           make_issue(state="CLOSED"))
        self.assertEqual(kind, "closed")
        self.assertIsNone(auto)


class TestNoProposalYet(unittest.TestCase):
    def test_builder_is_told_to_propose_or_plan(self):
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", make_issue())
        self.assertEqual(kind, "propose")
        self.assertIsNone(auto)

    def test_coordinator_is_told_to_review_decomposition_instead(self):
        kind, lines, auto = decide_action(
            make_cfg(["a"], coordinators=["coord"]), "coord", make_issue())
        self.assertEqual(kind, "coord-idle")


class TestReviewFlow(unittest.TestCase):
    def test_others_pending_proposal_needs_my_review(self):
        iss = make_issue(comments=[comment("propose", "a", rev=1)])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "b", iss)
        self.assertEqual(kind, "review")

    def test_already_reviewed_reports_current_verdict(self):
        iss = make_issue(comments=[
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "b", iss)
        self.assertEqual(kind, "reviewed")


class TestOwnProposalOutcome(unittest.TestCase):
    def test_builder_claims_automatically_when_agreed(self):
        iss = make_issue(comments=[
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "claim")
        self.assertEqual(auto, ["claim", "1"])

    def test_coordinator_cannot_auto_claim_even_when_agreed(self):
        iss = make_issue(comments=[
            comment("propose", "coord", seconds_ago=10, rev=1),
            comment("review", "a", seconds_ago=5, rev=1, verdict="AGREE"),
        ])
        kind, lines, auto = decide_action(
            make_cfg(["a"], coordinators=["coord"]), "coord", iss)
        self.assertEqual(kind, "coord-cant-claim")
        self.assertIsNone(auto)

    def test_revise_when_objected(self):
        iss = make_issue(comments=[
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="OBJECT"),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "revise")

    def test_wait_while_review_pending(self):
        iss = make_issue(comments=[comment("propose", "a", seconds_ago=10, rev=1)])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "wait")


class TestClaimedWork(unittest.TestCase):
    def test_my_claim_shows_wip_instructions(self):
        iss = make_issue(comments=[
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
            comment("claim", "a", seconds_ago=1),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "mine-wip")

    def test_someone_elses_claim_says_hands_off(self):
        iss = make_issue(comments=[
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
            comment("claim", "a", seconds_ago=1),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "b", iss)
        self.assertEqual(kind, "other-wip")


class TestPlannedChild(unittest.TestCase):
    def test_planned_child_not_owned_by_me(self):
        body = mark("planned", "coord", parent=1, owner="b")
        kind, lines, auto = decide_action(
            make_cfg(["a", "b"], coordinators=["coord"]), "a", make_issue(body=body))
        self.assertEqual(kind, "not-mine")

    def test_planned_child_owned_by_me_auto_claims_without_reconsensus(self):
        body = mark("planned", "coord", parent=1, owner="a")
        kind, lines, auto = decide_action(
            make_cfg(["a", "b"], coordinators=["coord"]), "a", make_issue(body=body))
        self.assertEqual(kind, "planned-claim")
        self.assertEqual(auto, ["claim", "1"])

    def test_planned_child_already_claimed_by_me_shows_wip(self):
        body = mark("planned", "coord", parent=1, owner="a")
        iss = make_issue(body=body, comments=[comment("claim", "a", seconds_ago=1)])
        kind, lines, auto = decide_action(
            make_cfg(["a", "b"], coordinators=["coord"]), "a", iss)
        self.assertEqual(kind, "mine-wip")


class TestPlanDecomposition(unittest.TestCase):
    def test_agreed_plan_triggers_apply(self):
        iss = make_issue(comments=[
            comment("plan", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "plan-apply")
        self.assertEqual(auto, ["plan", "1", "--apply"])

    def test_objected_plan_asks_for_revision(self):
        iss = make_issue(comments=[
            comment("plan", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="OBJECT"),
        ])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "plan-revise")

    def test_someone_elses_plan_needs_my_review(self):
        iss = make_issue(comments=[comment("plan", "a", seconds_ago=10, rev=1)])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "b", iss)
        self.assertEqual(kind, "plan-review")

    def test_plan_with_children_already_applied_falls_through_to_proposal_flow(self):
        """자식 체크리스트가 이미 붙었으면 이 이슈는 더 이상 '분해 대기' 가 아니라
        보통의 에픽으로 취급돼야 한다 (분해 분기 재적용 금지)."""
        body = "### 계획된 작업\n- [ ] #2 자식1\n"
        iss = make_issue(body=body, comments=[comment("plan", "a", seconds_ago=10, rev=1)])
        kind, lines, auto = decide_action(make_cfg(["a", "b"]), "b", iss)
        self.assertNotIn(kind, ("plan-apply", "plan-revise", "plan-review", "plan-wait"))


class TestEpic(unittest.TestCase):
    def test_epic_with_open_child_is_epic_open(self):
        body = "### 계획된 작업\n- [ ] #2 자식1\n"
        iss = make_issue(body=body, labels=["deputy:epic"])
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.return_value = {"state": "OPEN"}
            kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "epic-open")
        self.assertIsNone(auto)

    def test_epic_with_all_children_closed_is_epic_done(self):
        body = "### 계획된 작업\n- [ ] #2 자식1\n"
        iss = make_issue(body=body, labels=["deputy:epic"])
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.return_value = {"state": "CLOSED"}
            kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "epic-done")

    def test_epic_child_lookup_failure_keeps_it_open_not_done(self):
        """자식 조회가 실패해도 에픽을 섣불리 완료로 판단하면 안 된다."""
        body = "### 계획된 작업\n- [ ] #2 자식1\n"
        iss = make_issue(body=body, labels=["deputy:epic"])
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.return_value = None
            kind, lines, auto = decide_action(make_cfg(["a", "b"]), "a", iss)
        self.assertEqual(kind, "epic-open")


if __name__ == "__main__":
    unittest.main()
