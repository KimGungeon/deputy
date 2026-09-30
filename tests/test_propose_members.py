"""Ownership boundaries and unique member names (#11)."""
import unittest

from deputy_module import load

deputy = load()


def candidate(path, code=1, extra=()):
    return dict(path=path, code=code, files=1, exts={".py": code}, extra=list(extra))


class TestProposeMembers(unittest.TestCase):
    def test_fills_shortfall_with_noncode_directories(self):
        members, unowned = deputy.propose_members(
            [candidate("api"), candidate("docs", 0), candidate("settings", 0)], 3, False)
        self.assertEqual([m["owns"] for m in members], [["api"], ["docs"], ["settings"]])
        self.assertEqual(unowned, [])

    def test_absorbs_descendants_and_extra_but_not_similar_prefix(self):
        members, unowned = deputy.propose_members([
            candidate("services", extra=["tests/services"]),
            candidate("services/api", extra=["tests/api"]),
            candidate("services-x"), candidate("docs", 0),
            candidate(".hidden"), candidate("(루트 파일)")], 1, False)
        self.assertEqual(members[0]["owns"],
                         ["services", "services/api", "tests/api", "tests/services"])
        self.assertEqual(unowned, ["services-x", "docs", ".hidden", "(루트 파일)"])

    def test_coordinator_is_unique_even_with_lead_directory(self):
        members, _ = deputy.propose_members([candidate("lead")], 1)
        self.assertEqual(members[0]["name"], "lead")
        self.assertEqual(members[0]["role"], "coordinator")
        self.assertEqual(members[0]["owns"], [])
        self.assertEqual(len({m["name"] for m in members}), len(members))
        self.assertEqual(members[1]["role"], "builder")

    def test_coordinator_can_be_disabled(self):
        members, _ = deputy.propose_members([candidate("lead")], 1, False)
        self.assertEqual([m["name"] for m in members], ["lead"])
        self.assertEqual([m["role"] for m in members], ["builder"])

    def test_empty_candidates(self):
        members, unowned = deputy.propose_members([], 3)
        self.assertEqual(len(members), 1)
        self.assertEqual(unowned, [])

    def test_member_name_collision_uses_parent_then_numeric_suffix(self):
        used = set()
        names = [deputy.member_name("src/api", used) for _ in range(4)]
        self.assertEqual(names, ["api", "src-api", "src-api2", "src-api3"])
        self.assertEqual(used, set(names))

    def test_member_name_normalizes_and_falls_back(self):
        self.assertEqual(deputy.member_name("src/My_API", set()), "my-api")
        self.assertEqual(deputy.member_name("???", set()), "core")

    def test_describe_groups_languages_and_limits_to_top_two(self):
        text = deputy.describe(dict(exts={".py": 5, ".sh": 2, ".go": 1}, files=8))
        self.assertEqual(text, "Python · 셸, 파일 8개")
        self.assertEqual(deputy.describe(dict(exts={".unknown": 1}, files=1)),
                         "기타, 파일 1개")
