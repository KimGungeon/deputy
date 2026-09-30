"""Exercise the real launcher with fake executables, never live Claude agents."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


def bash_path():
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"),
                     os.environ.get("LOCALAPPDATA", "") + "/Programs"):
            path = Path(base) / "Git/bin/bash.exe"
            if path.exists():
                return str(path)
        return None  # WSL bash cannot run Windows Python wrappers below.
    return shutil.which("bash")


@unittest.skipUnless(bash_path(), "Git Bash or POSIX bash required")
class TestLauncher(unittest.TestCase):
    def launch(self, fail_member, only=False):
        with tempfile.TemporaryDirectory(prefix="deputy launcher ") as directory:
            root = Path(directory)
            (root / ".deputy").mkdir()
            (root / ".deputy/deputy.json").write_text(json.dumps({"members": [
                {"name": name, "owns": [name], "brief": "fixture"} for name in ("a", "b")]}),
                encoding="utf-8")
            stub = root / "stubs"
            stub.mkdir()
            scripts = {
                "deputy": "exit 0\n",
                "pgrep": "exit 0\n",
                "caffeinate": "exit 0\n",
                "python3": "exec " + shlex.quote(Path(sys.executable).as_posix()) + ' "$@"\n',
                "claude": 'printf "%s\\n" "$DEPUTY_MEMBER" >> "$AUDIT_LAUNCH_LOG"\n'
                          '[ "$DEPUTY_MEMBER" != "$AUDIT_FAIL_MEMBER" ] || exit 42\nexit 0\n',
            }
            for name, script in scripts.items():
                path = stub / name
                path.write_text("#!/bin/sh\n" + script, encoding="utf-8", newline="\n")
                path.chmod(0o755)
            env = dict(os.environ, AUDIT_FAIL_MEMBER=fail_member,
                       AUDIT_LAUNCH_LOG=(root / "attempts").as_posix())
            for key in ("QUIET", "MEMBERS_OVERRIDE", "DEPUTY_FORCE"):
                env.pop(key, None)
            launcher = Path(__file__).resolve().parents[1] / "bin/deputy-up.sh"
            result = subprocess.run([
                bash_path(), "--noprofile", "--norc", "-c",
                'stub="$1"; if command -v cygpath >/dev/null; then stub="$(cygpath -u "$stub")"; fi; '
                'export PATH="$stub:$PATH"; '
                '[ "$(command -v claude)" = "$stub/claude" ] || exit 98; '
                '[ "$(command -v deputy)" = "$stub/deputy" ] || exit 99; '
                'cd "$2"; shift 2; bash "$@"', "test",
                stub.as_posix(), root.as_posix(), launcher.as_posix(),
                *(["--only", "a"] if only else [])], env=env, capture_output=True,
                encoding="utf-8", timeout=30)
            self.assertTrue((root / "attempts").exists(), result.stdout + result.stderr)
            attempts = (root / "attempts").read_text().splitlines()
            return result, attempts

    def test_single_failure_is_reported_to_watch(self):
        result, attempts = self.launch("a", only=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(attempts, ["a"])

    def test_failure_does_not_skip_remaining_members(self):
        result, attempts = self.launch("a")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(attempts, ["a", "b"])

    def test_all_success_returns_zero(self):
        result, attempts = self.launch("none")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(attempts, ["a", "b"])
