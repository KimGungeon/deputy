"""validate_plan() 테스트.

이 검사가 통과시킨 나쁜 분해는 사람 없는 8시간을 통째로 태운다
(함수 docstring이 스스로 그렇게 말한다). 그래서 여기 있는 각 규칙이
실제로 걸러내는지 하나씩 확인한다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deputy_module import load

deputy = load()
validate_plan = deputy.validate_plan
MAX_PLAN_CHILDREN = deputy.MAX_PLAN_CHILDREN


def make_cfg(builders, coordinators=()):
    members = [{"name": b} for b in builders]
    members += [{"name": c, "role": "coordinator"} for c in coordinators]
    return {"members": members}


SUMMARY = "이 에픽은 인터페이스를 먼저 고정한 뒤 나머지를 병렬로 진행하도록 쪼갰다."
DONE_WHEN = "pytest -q tests/x.py 가 0으로 종료하고 픽스처 3건을 통과한다"
WHY = "다른 작업이 이 인터페이스에 의존하므로 먼저 고정해야 한다"


def child(title, owner, after=None, why=WHY, done_when=DONE_WHEN):
    c = {"title": title, "owner": owner, "why": why, "done_when": done_when}
    if after is not None:
        c["after"] = after
    return c


def plan(children, summary=SUMMARY):
    return {"summary": summary, "children": children}


class TestTopLevel(unittest.TestCase):
    def test_non_dict_plan(self):
        errs = validate_plan(make_cfg(["a"]), ["not", "a", "dict"], 1)
        self.assertEqual(errs, ["최상위가 객체가 아닙니다."])

    def test_short_summary_flagged(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan(
            [child("작업 하나 제목입니다", "a"), child("작업 둘 제목입니다", "b")],
            summary="너무 짧음"), 1)
        self.assertTrue(any("summary" in e for e in errs))

    def test_missing_children_short_circuits(self):
        errs = validate_plan(make_cfg(["a"]), {"summary": SUMMARY}, 1)
        self.assertEqual(errs, ["children 이 비어 있습니다."])

    def test_empty_children_list_short_circuits(self):
        errs = validate_plan(make_cfg(["a"]), plan([]), 1)
        self.assertEqual(errs, ["children 이 비어 있습니다."])

    def test_too_many_children(self):
        children = [child(f"작업 번호 {i} 제목입니다", "a") for i in range(MAX_PLAN_CHILDREN + 1)]
        errs = validate_plan(make_cfg(["a"]), plan(children), 1)
        self.assertTrue(any("상한" in e for e in errs))


class TestPerChild(unittest.TestCase):
    def test_title_too_short(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("짧음", "a"), child("정상적인 제목 길이입니다", "b"),
        ]), 1)
        self.assertTrue(any("title 이 너무 짧습니다" in e for e in errs))

    def test_duplicate_titles(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("똑같은 제목입니다", "a"),
            child("똑같은 제목입니다", "b"),
        ]), 1)
        self.assertTrue(any("중복" in e for e in errs))

    def test_owner_not_a_builder(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "ghost"),
        ]), 1)
        self.assertTrue(any("담당자가 아닙니다" in e for e in errs))

    def test_coordinator_cannot_own_a_child(self):
        errs = validate_plan(make_cfg(["a"], coordinators=["coord"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "coord"),
        ]), 1)
        self.assertTrue(any("조율자는 구현하지 않으므로" in e for e in errs))

    def test_why_too_short(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a", why="짧음"),
            child("정상적인 제목 둘입니다", "b"),
        ]), 1)
        self.assertTrue(any("why 가 너무 짧습니다" in e for e in errs))

    def test_done_when_too_short(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a", done_when="끝나면 끝"),
            child("정상적인 제목 둘입니다", "b"),
        ]), 1)
        self.assertTrue(any("done_when 이 너무 짧습니다" in e for e in errs))

    def test_done_when_without_verifiable_hint(self):
        vague = "충분히 잘 동작하는 것을 눈으로 확인하고 만족스러우면 끝낸다"
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a", done_when=vague),
            child("정상적인 제목 둘입니다", "b"),
        ]), 1)
        self.assertTrue(any("검증 가능하게" in e for e in errs))

    def test_after_must_be_int_list(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "b", after=["one"]),
        ]), 1)
        self.assertTrue(any("정수 배열" in e for e in errs))

    def test_after_out_of_range(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "b", after=[99]),
        ]), 1)
        self.assertTrue(any("범위를 벗어났습니다" in e for e in errs))

    def test_after_self_reference(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a", after=[1]),
            child("정상적인 제목 둘입니다", "b"),
        ]), 1)
        self.assertTrue(any("자기 자신을 선행으로 지정" in e for e in errs))


class TestGraphShape(unittest.TestCase):
    def test_cycle_detected(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a", after=[2]),
            child("정상적인 제목 둘입니다", "b", after=[1]),
        ]), 1)
        self.assertTrue(any("순환" in e for e in errs))

    def test_no_startable_task_without_cycle_via_bad_after_values(self):
        """순환은 없지만(2번의 after=3 은 존재하지 않는 자식) 모두가 선행을 갖고 있어
        아무도 먼저 시작할 수 없는 경우도 잡아야 한다."""
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a", after=[2]),
            child("정상적인 제목 둘입니다", "b", after=[99]),
        ]), 1)
        self.assertTrue(any("처음 시작할 수 있는 게 없습니다" in e for e in errs))

    def test_builder_with_a_startable_task_is_not_flagged(self):
        """b 의 작업 중 하나(child2)는 선행이 없으므로, 나머지가 after 를 가져도 문제없다."""
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "b"),
            child("정상적인 제목 셋입니다", "b", after=[1]),
        ]), 1)
        self.assertFalse(any("선행 없이 시작할 수 있는 작업이 없습니다" in e for e in errs))

    def test_builder_with_only_dependent_tasks_is_flagged(self):
        errs = validate_plan(make_cfg(["a", "b", "c"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "b", after=[1]),
            child("정상적인 제목 셋입니다", "c", after=[1]),
            child("정상적인 제목 넷입니다", "b", after=[2]),
        ]), 1)
        # b 는 시작 가능한 작업이 있다(첫 b 작업이 after=[1]... 아니 그것도 after 있음)
        # 실제로 b 의 모든 작업이 after 를 갖고 있어 놀게 되는 케이스
        self.assertTrue(any("'b' 에게는 선행 없이 시작할 수 있는 작업이 없습니다" in e for e in errs))

    def test_single_owner_with_multiple_builders_is_flagged(self):
        errs = validate_plan(make_cfg(["a", "b"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "a"),
        ]), 1)
        self.assertTrue(any("혼자 맡습니다" in e for e in errs))

    def test_single_owner_with_single_builder_is_fine(self):
        errs = validate_plan(make_cfg(["a"]), plan([
            child("정상적인 제목 하나입니다", "a"),
            child("정상적인 제목 둘입니다", "a", after=[1]),
        ]), 1)
        self.assertFalse(any("혼자 맡습니다" in e for e in errs))


class TestValidPlanPasses(unittest.TestCase):
    def test_well_formed_plan_has_no_errors(self):
        errs = validate_plan(make_cfg(["a", "b"], coordinators=["coord"]), plan([
            child("인터페이스 뼈대 확정", "a"),
            child("구현체 A 붙이기", "a", after=[1]),
            child("b 몫의 픽스처 준비", "b"),
            child("구현체 B 붙이기", "b", after=[1]),
        ]), 1)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
