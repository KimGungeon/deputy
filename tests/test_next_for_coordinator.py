"""next_for_coordinator(cfg, me, full, active, out) 는 deputy next 가 조율자에게
매 턴 찍어주는 우선순위 안내를 전부 결정한다. full/active 에 가짜 이슈
dict 를 넣어 테스트한다. 에픽의 자식 조회는 issue()를 모킹해
외부 요청 없이 검증한다. (이슈 #13)

builder 쪽 분기(cmd_next() 안에 인라인으로 남아 있음)와 '내 분해안 판정'(consensus()
의존) 은 범위 밖 - 이 이슈가 명시한 4케이스만 다룬다.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deputy_module import load

deputy = load()
next_for_coordinator = deputy.next_for_coordinator


def full_issue(number, title="이슈", url="http://x/1", labels=(), body="", comments=()):
    return {
        "number": number,
        "title": title,
        "url": url,
        "labels": [{"name": l} for l in labels],
        "body": body,
        "comments": list(comments),
    }


def marker_comment(kind, by, rev=None, verdict=None, at="2024-01-01T00:00:00Z", text=""):
    parts = [f"kind={kind}", f"by={by}"]
    if rev is not None:
        parts.append(f"rev={rev}")
    if verdict is not None:
        parts.append(f"verdict={verdict}")
    body = f"<!-- deputy v1 {' '.join(parts)} -->\n{text}"
    return {"body": body, "createdAt": at}


class TestNextForCoordinator(unittest.TestCase):
    def test_owed_proposal_appears_in_rank1(self):
        d = full_issue(
            5, title="테스트 이슈", labels=["deputy:next"],
            comments=[marker_comment("propose", "settings", rev=1)],
        )
        out = []
        next_for_coordinator({}, "bin", {5: d}, [], out)
        text = "\n".join(out)
        self.assertIn("[1순위]", text)
        self.assertIn("#5", text)

    def test_already_reviewed_same_rev_is_excluded(self):
        d = full_issue(
            5, title="테스트 이슈", labels=["deputy:next"],
            comments=[
                marker_comment("propose", "settings", rev=1, at="2024-01-01T00:00:00Z"),
                marker_comment("review", "bin", rev=1, verdict="AGREE",
                               at="2024-01-01T00:01:00Z"),
            ],
        )
        out = []
        next_for_coordinator({}, "bin", {5: d}, [], out)
        self.assertNotIn("[1순위]", "\n".join(out))

    def test_blocked_issue_appears_in_rank2_with_review_summary(self):
        d = full_issue(
            6, title="깨진 합의", labels=["deputy:blocked"],
            comments=[
                marker_comment("review", "lead", rev=1, verdict="OBJECT",
                               text="이 시점에 하면 안 된다"),
            ],
        )
        out = []
        next_for_coordinator({}, "bin", {6: d}, [], out)
        text = "\n".join(out)
        self.assertIn("합의가 깨진 이슈", text)
        self.assertIn("#6", text)
        self.assertIn("lead", text)
        self.assertIn("OBJECT", text)
        self.assertIn("이 시점에 하면 안 된다", text)

    def test_epic_with_all_children_closed_appears_in_rank2(self):
        epic_body = "### 파생 이슈\n- [ ] #2 자식1\n- [ ] #3 자식2\n"
        d = full_issue(1, title="완료된 에픽", labels=["deputy:epic"], body=epic_body)
        out = []
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.side_effect = lambda n, cached=False, check=True: {
                2: {"state": "CLOSED"}, 3: {"state": "CLOSED"},
            }.get(n)
            next_for_coordinator({}, "bin", {1: d}, [], out)
        text = "\n".join(out)
        self.assertIn("자식이 모두 닫힌 에픽", text)
        self.assertIn("#1", text)


if __name__ == "__main__":
    unittest.main()
