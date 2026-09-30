"""Independent acceptance oracle. Executed in a fresh process per workspace."""
import argparse
import copy
import importlib
import json
from pathlib import Path
import sys
import unittest


class Acceptance(unittest.TestCase):
    def test_a1(self):
        self.assertEqual(alpha.clean_name("  AlICE  "), "alice")
        self.assertEqual(alpha.clean_name(" 서울 "), "서울")
        for invalid in ("", "  ", None, 7):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                alpha.clean_name(invalid)

    def test_a2(self):
        self.assertEqual(alpha.parse_count(" 007 "), 7)
        self.assertEqual(alpha.parse_count("0"), 0)
        for value in ("-1", "+1", "1.5", "", "１２", "1e3", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                alpha.parse_count(value)

    def test_a3(self):
        self.assertEqual(alpha.parse_csv("name,count\n Bob , 3 \n\n"), [{"name":"bob","count":3}])
        self.assertEqual(alpha.parse_csv("name,count\n"), [])
        for text in ("wrong,count\na,1\n", "name,count\na\n", "name,count\na,-1\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                alpha.parse_csv(text)

    def test_a4(self):
        rows = [{"name":"b","count":2}, {"name":"a","count":1}, {"name":"b","count":3}]
        saved = copy.deepcopy(rows)
        self.assertEqual(alpha.combine(rows), [{"name":"b","count":5},{"name":"a","count":1}])
        self.assertEqual(rows, saved)
        self.assertEqual(alpha.combine([]), [])

    def test_b1(self):
        self.assertEqual(beta.summarize([]), {"records":0,"total":0,"maximum":0})
        self.assertEqual(beta.summarize([{"name":"x","count":2},{"name":"y","count":5}]),
                         {"records":2,"total":7,"maximum":5})

    def test_b2(self):
        rows = [{"name":"b","count":2},{"name":"a","count":2},{"name":"z","count":9}]
        saved = copy.deepcopy(rows)
        self.assertEqual(beta.top_names(rows, 2), ["z", "a"])
        self.assertEqual(beta.top_names(rows, 0), [])
        self.assertEqual(rows, saved)
        with self.assertRaises(ValueError):
            beta.top_names(rows, -1)

    def test_b3(self):
        self.assertEqual(beta.render({"z":"서울","a":1}), '{"a":1,"z":"서울"}\n')

    def test_b4(self):
        self.assertEqual(json.loads(beta.from_csv("name,count\na,2\nb,4\n")),
                         {"records":2,"total":6,"maximum":4})

    def test_i1(self):
        self.assertEqual(alpha.combine(alpha.parse_csv('name,count\n"A, B",2\n"a, b",3\n')),
                         [{"name":"a, b","count":5}])

    def test_i2(self):
        for text in ("name,count\na,1,EXTRA\n", "name,count\n ,1\n", "name,count\na,\n", ""):
            with self.subTest(text=text), self.assertRaises(ValueError):
                alpha.parse_csv(text)

    def test_i3(self):
        self.assertEqual(beta.from_csv("name,count\n"), '{"maximum":0,"records":0,"total":0}\n')

    def test_i4(self):
        self.assertEqual(beta.from_csv("name,count\n서울,2\n서울,3\n부산,1\n"),
                         '{"maximum":5,"records":2,"total":6}\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--case", choices=[n for n in dir(Acceptance) if n.startswith("test_")])
    args = parser.parse_args()
    sys.path.insert(0, str(args.workspace.resolve()))
    global alpha, beta
    alpha = importlib.import_module("alpha.normalize")
    beta = importlib.import_module("beta.report")
    suite = (unittest.TestSuite([Acceptance(args.case)]) if args.case else
             unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
