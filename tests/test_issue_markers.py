"""파생/계획 마커 파싱과 에픽 진행률 판정 테스트.

parent_of/is_derived/planned_meta/children_of 는 이슈 본문에서 상태를 복원하는
유일한 방법이다(로컬에 별도 저장소가 없다는 것이 이 프로젝트의 핵심 설계다).
epic_state 는 자식 조회가 실패했을 때 에픽을 섣불리 '완료'로 오판하지 않는지가
무인 운영 안전성의 핵심이라 별도로 검증한다.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deputy_module import load

deputy = load()
parent_of = deputy.parent_of
is_derived = deputy.is_derived
planned_meta = deputy.planned_meta
children_of = deputy.children_of
epic_state = deputy.epic_state


def issue_with_body(body, number=1, labels=()):
    return {"number": number, "body": body, "labels": [{"name": l} for l in labels]}


class TestDeriveMark(unittest.TestCase):
    def test_parent_of_derive(self):
        iss = issue_with_body("<!-- deputy v1 kind=derive by=a parent=7 -->\n본문")
        self.assertEqual(parent_of(iss), 7)
        self.assertTrue(is_derived(iss))

    def test_no_marker_has_no_parent(self):
        iss = issue_with_body("그냥 본문입니다")
        self.assertIsNone(parent_of(iss))
        self.assertFalse(is_derived(iss))

    def test_planned_child_is_not_derived(self):
        iss = issue_with_body(
            "<!-- deputy v1 kind=planned by=a parent=7 owner=b -->\n본문")
        self.assertEqual(parent_of(iss), 7)
        self.assertFalse(is_derived(iss))

    def test_planned_meta_parses_after_list(self):
        iss = issue_with_body(
            "<!-- deputy v1 kind=planned by=a parent=7 owner=b after=3,4 -->\n본문")
        meta = planned_meta(iss)
        self.assertEqual(meta, {"parent": 7, "owner": "b", "after": [3, 4]})

    def test_planned_meta_without_after(self):
        iss = issue_with_body(
            "<!-- deputy v1 kind=planned by=a parent=7 owner=b -->\n본문")
        meta = planned_meta(iss)
        self.assertEqual(meta, {"parent": 7, "owner": "b", "after": []})

    def test_planned_meta_none_when_not_planned(self):
        iss = issue_with_body("<!-- deputy v1 kind=derive by=a parent=7 -->\n본문")
        self.assertIsNone(planned_meta(iss))


class TestChildrenOf(unittest.TestCase):
    def test_extracts_child_numbers_from_checklist(self):
        body = (
            "### 파생 이슈\n"
            "- [ ] #12 첫번째\n"
            "- [x] #13 두번째\n"
        )
        self.assertEqual(children_of(issue_with_body(body)), [12, 13])

    def test_no_checklist_means_no_children(self):
        self.assertEqual(children_of(issue_with_body("아무 체크리스트도 없음")), [])


class TestEpicState(unittest.TestCase):
    def test_epic_with_all_children_closed_is_done(self):
        epic_body = "### 계획된 작업\n- [ ] #2 자식1\n- [ ] #3 자식2\n"
        full = {1: issue_with_body(epic_body, number=1, labels=["deputy:epic"])}
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.side_effect = lambda n, cached=False, check=True: {
                2: {"state": "CLOSED"}, 3: {"state": "CLOSED"},
            }.get(n)
            done, ongoing = epic_state(full)
        self.assertEqual(len(done), 1)
        self.assertEqual(len(ongoing), 0)

    def test_epic_with_one_open_child_is_ongoing(self):
        epic_body = "### 계획된 작업\n- [ ] #2 자식1\n- [ ] #3 자식2\n"
        full = {1: issue_with_body(epic_body, number=1, labels=["deputy:epic"])}
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.side_effect = lambda n, cached=False, check=True: {
                2: {"state": "CLOSED"}, 3: {"state": "OPEN"},
            }.get(n)
            done, ongoing = epic_state(full)
        self.assertEqual(len(done), 0)
        self.assertEqual(len(ongoing), 1)

    def test_lookup_failure_is_treated_as_still_open_not_done(self):
        """자식 조회가 실패해 None 이 오면, 닫힌 것으로 오판해 에픽을 섣불리
        완료 처리하면 안 된다. 실패는 안전한 쪽(진행 중)으로 취급해야 한다."""
        epic_body = "### 계획된 작업\n- [ ] #2 자식1\n"
        full = {1: issue_with_body(epic_body, number=1, labels=["deputy:epic"])}
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.return_value = None
            done, ongoing = epic_state(full)
        self.assertEqual(len(done), 0)
        self.assertEqual(len(ongoing), 1)

    def test_non_epic_issue_is_ignored(self):
        full = {1: issue_with_body("본문", number=1, labels=[])}
        with mock.patch.object(deputy, "issue") as fake_issue:
            fake_issue.return_value = None
            done, ongoing = epic_state(full)
        self.assertEqual(done, [])
        self.assertEqual(ongoing, [])


if __name__ == "__main__":
    unittest.main()
