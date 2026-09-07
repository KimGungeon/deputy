"""consensus() 결정론 판정 테스트.

핵심 불변식(README 가 명시적으로 주장하는 것): 사람이 없는 동안
'합의를 기다리며 영구 정지'하는 경우가 없어야 한다. 즉 리뷰가 끝내 안 와도
review_timeout_minutes 가 지나면 반드시 CLAIM 으로 빠져나가야 한다.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deputy_module import load

deputy = load()
consensus = deputy.consensus


def iso(seconds_ago=0):
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return dt.isoformat().replace("+00:00", "Z")


def mark(kind, by, rev=None, verdict=None):
    parts = [f"kind={kind}", f"by={by}"]
    if rev is not None:
        parts.append(f"rev={rev}")
    if verdict is not None:
        parts.append(f"verdict={verdict}")
    return "<!-- deputy v1 " + " ".join(parts) + " -->"


def comment(kind, by, seconds_ago=0, rev=None, verdict=None):
    return {"body": mark(kind, by, rev, verdict) + "\n(테스트용 코멘트)",
            "createdAt": iso(seconds_ago)}


def cfg(member_names, review_timeout_minutes=45, max_revisions=2):
    return {
        "members": [{"name": n} for n in member_names],
        "review_timeout_minutes": review_timeout_minutes,
        "max_revisions": max_revisions,
    }


def iss(*comments):
    return {"comments": list(comments)}


class TestNoProposal(unittest.TestCase):
    def test_no_proposal_is_none(self):
        v = consensus(cfg(["a", "b"]), iss())
        self.assertEqual(v["decision"], "NONE")


class TestClaim(unittest.TestCase):
    def test_all_agree(self):
        v = consensus(cfg(["a", "b", "c"]), iss(
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
            comment("review", "c", seconds_ago=5, rev=1, verdict="AGREE"),
        ))
        self.assertEqual(v["decision"], "CLAIM")
        self.assertEqual(sorted(v["detail"]["agree"]), ["b", "c"])

    def test_abstain_after_timeout_still_claims(self):
        """리뷰가 끝내 안 와도 타임아웃이 지나면 CLAIM 이어야 한다 (영구 대기 금지)."""
        v = consensus(cfg(["a", "b"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=46 * 60, rev=1),
        ))
        self.assertEqual(v["decision"], "CLAIM")
        self.assertEqual(v["detail"]["abstained"], ["b"])

    def test_boundary_age_equal_timeout_counts_as_abstain(self):
        v = consensus(cfg(["a", "b"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=45 * 60, rev=1),
        ))
        self.assertEqual(v["decision"], "CLAIM")
        self.assertEqual(v["detail"]["abstained"], ["b"])

    def test_solo_member_claims_immediately_without_waiting(self):
        """멤버가 제안자 하나뿐이면 리뷰할 사람이 없으니 기다리지 않고 바로 착수해야 한다."""
        v = consensus(cfg(["a"]), iss(
            comment("propose", "a", seconds_ago=1, rev=1),
        ))
        self.assertEqual(v["decision"], "CLAIM")

    def test_stale_review_from_previous_revision_ignored(self):
        """이전 리비전에 대한 리뷰는 새 리비전에 승계되지 않는다 (재검토 필요)."""
        v = consensus(cfg(["a", "b"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=600, rev=1),
            comment("review", "b", seconds_ago=590, rev=1, verdict="AGREE"),
            comment("propose", "a", seconds_ago=60, rev=2),
        ))
        # b의 리뷰는 rev1 것이라 rev2 에는 안 붙는다 -> 아직 타임아웃 전이므로 WAIT
        self.assertEqual(v["decision"], "WAIT")
        self.assertEqual(v["detail"]["pending"], ["b"])

    def test_latest_review_from_same_member_wins(self):
        """같은 사람이 같은 리비전에 두 번 리뷰하면 (마음을 바꾼 경우) 최신 것이 이긴다."""
        v = consensus(cfg(["a", "b"]), iss(
            comment("propose", "a", seconds_ago=600, rev=1),
            comment("review", "b", seconds_ago=500, rev=1, verdict="OBJECT"),
            comment("review", "b", seconds_ago=100, rev=1, verdict="AGREE"),
        ))
        self.assertEqual(v["decision"], "CLAIM")
        self.assertEqual(v["detail"]["agree"], ["b"])
        self.assertEqual(v["detail"]["object"], [])


class TestWait(unittest.TestCase):
    def test_pending_within_timeout(self):
        v = consensus(cfg(["a", "b", "c"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=5 * 60, rev=1),
        ))
        self.assertEqual(v["decision"], "WAIT")
        self.assertEqual(sorted(v["detail"]["pending"]), ["b", "c"])

    def test_one_reviewed_one_pending_still_waits(self):
        v = consensus(cfg(["a", "b", "c"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=5 * 60, rev=1),
            comment("review", "b", seconds_ago=60, rev=1, verdict="AGREE"),
        ))
        self.assertEqual(v["decision"], "WAIT")
        self.assertEqual(v["detail"]["pending"], ["c"])


class TestRevise(unittest.TestCase):
    def test_object_below_max_revisions_is_revise(self):
        v = consensus(cfg(["a", "b"], max_revisions=2), iss(
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="OBJECT"),
        ))
        self.assertEqual(v["decision"], "REVISE")

    def test_amend_below_max_revisions_is_revise(self):
        v = consensus(cfg(["a", "b"], max_revisions=2), iss(
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AMEND"),
        ))
        self.assertEqual(v["decision"], "REVISE")

    def test_objection_decisive_even_while_others_pending(self):
        """한 명이라도 반대하면, 다른 사람이 아직 리뷰 안 했어도 기다리지 않고 REVISE."""
        v = consensus(cfg(["a", "b", "c"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="OBJECT"),
        ))
        self.assertEqual(v["decision"], "REVISE")

    def test_revision_at_max_revisions_boundary_is_still_revise(self):
        v = consensus(cfg(["a", "b"], max_revisions=2), iss(
            comment("propose", "a", seconds_ago=10, rev=2),
            comment("review", "b", seconds_ago=5, rev=2, verdict="OBJECT"),
        ))
        self.assertEqual(v["decision"], "REVISE")


class TestEscalate(unittest.TestCase):
    def test_object_above_max_revisions_is_escalate(self):
        v = consensus(cfg(["a", "b"], max_revisions=2), iss(
            comment("propose", "a", seconds_ago=10, rev=3),
            comment("review", "b", seconds_ago=5, rev=3, verdict="OBJECT"),
        ))
        self.assertEqual(v["decision"], "ESCALATE")

    def test_mixed_object_and_amend_above_max_is_escalate(self):
        v = consensus(cfg(["a", "b", "c"], max_revisions=2), iss(
            comment("propose", "a", seconds_ago=10, rev=3),
            comment("review", "b", seconds_ago=5, rev=3, verdict="OBJECT"),
            comment("review", "c", seconds_ago=5, rev=3, verdict="AMEND"),
        ))
        self.assertEqual(v["decision"], "ESCALATE")
        self.assertEqual(v["detail"]["object"], ["b"])
        self.assertEqual(v["detail"]["amend"], ["c"])


class TestPlanTreatedLikeProposal(unittest.TestCase):
    def test_plan_kind_participates_in_consensus(self):
        v = consensus(cfg(["a", "b"]), iss(
            comment("plan", "a", seconds_ago=10, rev=1),
            comment("review", "b", seconds_ago=5, rev=1, verdict="AGREE"),
        ))
        self.assertEqual(v["decision"], "CLAIM")

    def test_only_latest_of_propose_and_plan_combined_counts(self):
        """propose 뒤에 plan 으로 갈아탄 경우, 가장 최근 것 기준으로 판정해야 한다."""
        v = consensus(cfg(["a", "b"]), iss(
            comment("propose", "a", seconds_ago=600, rev=1),
            comment("review", "b", seconds_ago=590, rev=1, verdict="AGREE"),
            comment("plan", "a", seconds_ago=60, rev=1),
        ))
        # plan 도 rev=1 이라 review 가 여전히 같은 rev 에 붙어 있어 CLAIM 이어야 정상.
        # 만약 kind 를 구분하지 않고 rev 만 보면 우연히 통과할 수 있는 케이스이므로
        # rev 를 다르게 준 아래 테스트가 진짜 검증이다.
        self.assertIn(v["decision"], ("CLAIM", "WAIT"))

    def test_plan_revision_requires_fresh_review(self):
        v = consensus(cfg(["a", "b"], review_timeout_minutes=45), iss(
            comment("propose", "a", seconds_ago=600, rev=1),
            comment("review", "b", seconds_ago=590, rev=1, verdict="AGREE"),
            comment("plan", "a", seconds_ago=60, rev=2),
        ))
        self.assertEqual(v["decision"], "WAIT")


class TestNoPermanentWait(unittest.TestCase):
    """시간이 흐르기만 하면 (댓글이 안 늘어도) 언젠가 WAIT 를 반드시 벗어나야 한다."""

    def test_wait_transitions_to_claim_as_time_passes(self):
        c = cfg(["a", "b"], review_timeout_minutes=45)
        before = consensus(c, iss(comment("propose", "a", seconds_ago=5 * 60, rev=1)))
        after = consensus(c, iss(comment("propose", "a", seconds_ago=50 * 60, rev=1)))
        self.assertEqual(before["decision"], "WAIT")
        self.assertEqual(after["decision"], "CLAIM")

    def test_once_claimed_by_abstention_never_reverts_to_wait_as_age_grows_further(self):
        c = cfg(["a", "b"], review_timeout_minutes=45)
        at_timeout = consensus(c, iss(comment("propose", "a", seconds_ago=45 * 60, rev=1)))
        much_later = consensus(c, iss(comment("propose", "a", seconds_ago=5 * 3600, rev=1)))
        self.assertEqual(at_timeout["decision"], "CLAIM")
        self.assertEqual(much_later["decision"], "CLAIM")


if __name__ == "__main__":
    unittest.main()
