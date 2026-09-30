import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.runner import live
from validation.runner.workspace import prepare, read, write


class TestLiveAdapter(unittest.TestCase):
    def make_manifest(self):
        root = Path(tempfile.mkdtemp(prefix="validation-live-"))
        folder = prepare("run-live", root)
        manifest = read(folder / "manifest.json")
        manifest.update(mode="live", repository="owner/deputy-validation-test",
                        issues={str(i):i for i in range(12)}, model="test-model",
                        cost_meter="fixture-meter")
        write(folder / "manifest.json", manifest)
        return folder, manifest

    def test_live_manifest_rejects_missing_cost_meter(self):
        folder, manifest = self.make_manifest()
        manifest["cost_meter"] = None
        write(folder / "manifest.json", manifest)
        with self.assertRaises(RuntimeError):
            live.observe(folder)

    def test_launch_dry_run_has_no_process_and_uses_pinned_cwd(self):
        folder, manifest = self.make_manifest()
        with mock.patch.object(live, "claude_executable", return_value="claude.cmd"), \
                mock.patch.object(live.subprocess, "run") as run:
            result = live.launch(folder, dry_run=True)
        run.assert_not_called()
        self.assertEqual(result["workspace"], manifest["workspace"])
        self.assertEqual(len(result["commands"]), 3)
        self.assertTrue(all(command[1:3] == ["--bg", "--name"] for command in result["commands"]))

    def test_observe_filters_foreign_and_unregistered_sessions(self):
        folder, manifest = self.make_manifest()
        rows = [{"id":"local","sessionId":"local","name":"deputy-alpha",
                 "cwd":manifest["workspace"],"status":"busy"},
                {"id":"foreign","sessionId":"foreign","name":"deputy-alpha",
                 "cwd":manifest["workspace"] + "-other","status":"busy"},
                {"id":"unknown","sessionId":"unknown","name":"deputy-beta",
                 "cwd":manifest["workspace"],"status":"busy"}]
        manifest["sessions"] = {"alpha":"local"}
        write(folder / "manifest.json", manifest)
        fake = mock.Mock(returncode=0, stdout=json.dumps(rows), stderr="")
        with mock.patch.object(live, "claude_executable", return_value="claude.cmd"), \
                mock.patch.object(live.subprocess, "run", return_value=fake) as run:
            result = live.observe(folder)
        self.assertEqual([row["id"] for row in result], ["local"])
        self.assertIn("--cwd", run.call_args.args[0])

    def test_stop_only_targets_manifest_ids(self):
        folder, manifest = self.make_manifest()
        manifest["sessions"] = {"alpha":"local", "beta":"also-local"}
        write(folder / "manifest.json", manifest)
        with mock.patch.object(live, "claude_executable", return_value="claude.cmd"), \
                mock.patch.object(live.subprocess, "run") as run:
            result = live.stop(folder, dry_run=True)
        run.assert_not_called()
        self.assertEqual([command[-1] for command in result["commands"]], ["local", "also-local"])
