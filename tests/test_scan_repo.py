"""scan_repo() 는 `deputy init`/`deputy scan` 이 멤버 구성을 자동 제안할 때
쓰는 핵심 로직이다. git 이 추적하는 파일만 보고, 컨테이너 디렉터리(src/ 등)는
한 단계 더 들어가고, 테스트 디렉터리는 대응하는 코드 디렉터리에 흡수해야 한다.
실제 git 저장소를 임시로 만들어 이 규칙들을 검증한다.
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deputy_module import load

deputy = load()
scan_repo = deputy.scan_repo
shebang_ext = deputy.shebang_ext


def write(root, rel, content="x = 1\n"):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def make_repo(files):
    tmp = tempfile.mkdtemp(prefix="deputy-scan-")
    subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
    for rel, content in files.items():
        write(tmp, rel, content)
    subprocess.run(["git", "-C", tmp, "add", "-A"], check=True)
    return tmp


class TestScanRepo(unittest.TestCase):
    def test_container_dir_descends_one_level(self):
        tmp = make_repo({
            "src/api/handler.py": "x = 1\n",
            "src/api/routes.py": "x = 1\n",
            "src/web/App.tsx": "const x = 1;\n",
        })
        cands = scan_repo(tmp)
        paths = {c["path"] for c in cands}
        self.assertIn("src/api", paths)
        self.assertIn("src/web", paths)
        self.assertNotIn("src", paths)

    def test_test_dir_absorbed_into_matching_code_dir(self):
        tmp = make_repo({
            "src/api/handler.py": "x = 1\n",
            "tests/api/test_handler.py": "x = 1\n",
        })
        cands = scan_repo(tmp)
        paths = {c["path"] for c in cands}
        self.assertIn("src/api", paths)
        self.assertNotIn("tests/api", paths)
        api = next(c for c in cands if c["path"] == "src/api")
        self.assertEqual(api["files"], 2)
        self.assertEqual(api.get("extra"), ["tests/api"])

    def test_skip_dirs_are_ignored_entirely(self):
        tmp = make_repo({
            "src/api/handler.py": "x = 1\n",
            "node_modules/leftpad/index.js": "x = 1\n",
        })
        cands = scan_repo(tmp)
        paths = {c["path"] for c in cands}
        self.assertTrue(all("node_modules" not in p for p in paths))

    def test_root_files_bucketed_separately(self):
        tmp = make_repo({"README.md": "# hi\n", "src/api/handler.py": "x=1\n"})
        cands = scan_repo(tmp)
        paths = {c["path"] for c in cands}
        self.assertIn("(루트 파일)", paths)

    def test_flat_top_level_dir_without_container_name_is_its_own_unit(self):
        tmp = make_repo({
            "backend/main.go": "package main\n",
            "frontend/index.js": "console.log(1)\n",
        })
        cands = scan_repo(tmp)
        paths = {c["path"] for c in cands}
        self.assertEqual(paths, {"backend", "frontend"})

    def test_sorted_by_code_volume_descending(self):
        tmp = make_repo({
            "big/a.py": "x=1\n", "big/b.py": "x=1\n", "big/c.py": "x=1\n",
            "small/a.py": "x=1\n",
        })
        cands = scan_repo(tmp)
        self.assertEqual(cands[0]["path"], "big")

    def test_extensionless_executable_uses_shebang(self):
        tmp = make_repo({})
        write(tmp, "bin/tool", "#!/usr/bin/env python3\nprint(1)\n")
        subprocess.run(["git", "-C", tmp, "add", "-A"], check=True)
        cands = scan_repo(tmp)
        bin_cand = next(c for c in cands if c["path"] == "bin")
        self.assertIn(".py", bin_cand["exts"])


class TestShebangExt(unittest.TestCase):
    def test_python_shebang(self):
        tmp = tempfile.mktemp()
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env python3\n")
        try:
            self.assertEqual(shebang_ext(tmp), ".py")
        finally:
            os.remove(tmp)

    def test_no_shebang_returns_empty(self):
        tmp = tempfile.mktemp()
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("just text\n")
        try:
            self.assertEqual(shebang_ext(tmp), "")
        finally:
            os.remove(tmp)

    def test_unknown_interpreter_falls_back_to_sh(self):
        tmp = tempfile.mktemp()
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env someweirdlang\n")
        try:
            self.assertEqual(shebang_ext(tmp), ".sh")
        finally:
            os.remove(tmp)


if __name__ == "__main__":
    unittest.main()
