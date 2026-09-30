"""Drive real deputy commands through a subprocess-backed fake service.

No model inference, parallel agents or real GitHub writes are performed here.
"""
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
from pathlib import Path
import subprocess
import sys
import time

from .control import Controller, Limits
from .reference import ALPHA, BETA
from .workspace import check, load_run, read, write


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class FakeBoundary:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / "fake-state.json"

    def call(self, service, args):
        return subprocess.run([sys.executable, str(Path(__file__).with_name("fake_cli.py")),
                               str(self.path), service, *args], capture_output=True,
                              text=True, encoding="utf-8", timeout=10)

    def gh(self, args, check=True, parse=False):
        result = self.call("gh", args)
        if result.returncode:
            if check:
                raise SystemExit(result.returncode)
            return None
        return json.loads(result.stdout) if parse else result.stdout

    def claude(self, args, timeout=30):
        require(args[0] == "claude", "Rehearsal refused non-Claude external command")
        result = self.call("claude", args[1:])
        return result.stdout if result.returncode == 0 else None

    def mutate(self, fn):
        state = read(self.path)
        fn(state)
        write(self.path, state)

    def fault(self, key):
        self.mutate(lambda s: s["faults"].update({key:1}))


def load_deputy(path):
    loader = SourceFileLoader("validation_deputy", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def rehearse(folder):
    folder = Path(folder).resolve()
    manifest = load_run(folder)
    require(manifest["status"] == "prepared", "Rehearsal requires a fresh run")
    started = time.monotonic()
    events = []
    scenarios = []
    manifest.update(status="running", mode="scripted_rehearsal")
    write(folder / "manifest.json", manifest)
    boundary = FakeBoundary(folder)
    deputy = load_deputy(Path(manifest["package"]) / "bin/deputy")
    cfg = read(Path(manifest["workspace"]) / ".deputy/deputy.json")
    tasks = read(folder / "tasks.json")
    state = {"sequence":0,"epoch":(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
             "workspace":manifest["workspace"],"issues":{},"sessions":[],"faults":{},"calls":[],
             "labels":list(deputy.LABELS)}
    for number, task in enumerate(tasks, 1):
        state["issues"][str(number)] = dict(number=number, title=f"[{task['id']}] {task['title']}",
            body=f"Owner: {task['owner']}; dependencies: {task['after']}", state="OPEN",
            labels=[], assignees=[], comments=[], url=f"https://example.invalid/issues/{number}")
    write(boundary.path, state)
    deputy.gh = boundary.gh
    deputy.gh_free = boundary.claude
    deputy.repo_root = lambda: manifest["workspace"]
    # Authentication data and watch history must never touch the user's HOME.
    deputy.job_details = lambda: {}
    deputy.watch_state_path = lambda: str(folder / "fake-watch-state.json")

    def event(kind, **data):
        item = {"at":datetime.now(timezone.utc).isoformat(),"kind":kind, **data}
        events.append(item)
        with (folder / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def invoke(member, *argv, expected=0):
        deputy.ISSUE_CACHE.clear()
        parsed = deputy.main_parser().parse_args(["--as", member, *map(str, argv)])
        output = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                parsed.fn(cfg, parsed)
            except SystemExit as exc:
                code = exc.code
        event("deputy", member=member, args=list(argv), returncode=code, output=output.getvalue())
        require(code == expected, f"Unexpected exit {code} for {argv}: {output.getvalue()}")
        return output.getvalue()

    def passed(sid, evidence):
        scenarios.append({"id":sid,"status":"PASS","execution":"synthetic","evidence":evidence})
        event("scenario", **scenarios[-1])

    controller = Controller(Limits(**manifest["limits"]))
    failure = None
    try:
        require(check(folder, label="baseline") != 0, "Fixture unexpectedly passes before implementation")
        event("baseline", result="expected_failure")
        # Deliberate scripted reference edits test the oracle, not agent intelligence.
        for name, content in (("alpha/normalize.py", ALPHA), ("beta/report.py", BETA)):
            (Path(manifest["workspace"]) / name).write_text(content, encoding="utf-8")
        require(check(folder, label="reference") == 0, "Reference answers failed acceptance checks")
        event("reference_applied", agent_generated=False)

        boundary.fault("launch")
        require(boundary.claude(["claude","--bg","--name","deputy-alpha"]) is None,
                "Injected launch failure was hidden")
        require(not read(boundary.path)["sessions"], "Failed launch created a fake session")
        require(controller.reserve_restart("alpha"), "Retry unexpectedly denied")
        for member in manifest["members"]:
            ident = boundary.claude(["claude","--bg","--name",f"deputy-{member}"])
            require(ident is not None, "Fake launch failed")
            manifest["sessions"][member] = ident
        passed("S3", "Failed fake CLI start created no session; bounded retry succeeded. Shell propagation is covered by test_launcher.py.")

        boundary.mutate(lambda s: s["sessions"].append(dict(id="foreign",sessionId="foreign",
            name="deputy-alpha",cwd=manifest["workspace"] + "-foreign",status="busy",startedAt=999999)))
        selected = deputy.session_states(cfg)
        require(selected["alpha"]["id"] != "foreign", "Foreign session selected")
        passed("S4", "Production session_states filtered a newer same-name foreign cwd.")

        for number, task in enumerate(tasks, 1):
            require(all(read(boundary.path)["issues"][str(i+1)]["state"] == "CLOSED"
                        for i, t in enumerate(tasks) if t["id"] in task["after"]), "Dependency unfinished")
            owner = task["owner"]
            invoke(owner, "propose", number, "--why", "Repair the seeded acceptance contract",
                   "--alternatives", "Other tasks have unmet dependencies", "--done-when", task["check"])
            for reviewer in manifest["members"]:
                if reviewer != owner:
                    invoke(reviewer, "review", number, "--verdict", "AGREE", "--reason",
                           "Scripted rehearsal: acceptance contract and dependency order checked")
            invoke(owner, "claim", number)
            if number == 1:
                boundary.gh(["issue","comment",str(number),"--body","HUMAN: apply the updated criterion"])
                invoke("beta", "note", number, "Unrelated progress")
                require("HUMAN:" in invoke(owner, "next"), "Human directive hidden by note")
                issue = deputy.issue(number)
                human = deputy.pending_human_comments(issue, owner)[0]
                invoke(owner, "ack", number, "--comment", deputy.human_comment_ref(human), "--result", "Applied criterion")
                require(not deputy.pending_human_comments(deputy.issue(number), owner), "Ack not recognized")
                require(deputy.pending_human_comments(deputy.issue(number), "beta"), "Ack leaked to another member")
                def edit(s):
                    next(c for c in s["issues"][str(number)]["comments"] if c["id"] == human["id"])["body"] += " EDITED"
                boundary.mutate(edit)
                require("EDITED" in invoke(owner, "next"), "Edited directive did not reappear")
                passed("S1", "Real next/ack logic preserved instructions across note, per-member ack and edit.")
            if number == 2:
                boundary.fault("close")
                before = deputy.issue(number)
                invoke(owner,"done",number,"--close","--no-next","--result","fixture check passed", expected=1)
                after = deputy.issue(number)
                require(before["labels"] == after["labels"] and before["assignees"] == after["assignees"],
                        "Failed close lost tracking")
                require(not any(c["kind"] == "done" for c in deputy.deputy_comments(after)), "False done marker")
                passed("S5", "Failed close retained tracking and emitted no done marker; subsequent retry verified CLOSED.")
            if number == 3:
                boundary.gh(["issue","comment",str(number),"--body","<!-- deputy v1 kind=claim by=beta -->"])
                invoke("beta", "note", number, "Lost race; withdrew")
                require(deputy.claim_owner(deputy.issue(number)) == owner, "Losing claim changed owner")
                require(deputy.decide_action(cfg,"beta",deputy.issue(number))[0] == "other-wip", "Loser directed to implement")
                passed("S2", "Recorded race ordering replayed; actual concurrent timing is NOT measured.")
            require(check(folder, task["check"], task["id"]) == 0, f"Acceptance failed: {task['id']}")
            invoke(owner,"done",number,"--close","--no-next","--result",f"Independent {task['check']} passed")
            require(deputy.issue(number)["state"] == "CLOSED", "Close not verified")

        boundary.fault("query")
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                deputy.session_states(cfg)
            except SystemExit:
                pass
            else:
                raise AssertionError("Failed session discovery was accepted")
        require(controller.observe(elapsed=1,cost_usd=0,remaining=0) == "confirm_completion", "Completion not confirmed twice")
        require(not controller.reserve_restart("alpha"), "Restarted during completion confirmation")
        require(controller.observe(elapsed=2,cost_usd=0,remaining=0) == "completed", "Completion not detected")
        passed("S6", "Discovery failure stopped production selection; controller required two completion observations and refused restart.")
    except (Exception, SystemExit) as exc:
        failure = f"{type(exc).__name__}: {exc}"
        event("failure", message=failure)
    finally:
        # Stop only manifest-registered IDs in this fake cwd, never the foreign row.
        for ident in manifest["sessions"].values():
            boundary.claude(["claude","stop",ident])
        snapshot = read(boundary.path)
        if any(s["id"] == "foreign" and s["status"] != "busy" for s in snapshot["sessions"]):
            failure = failure or "Foreign session was stopped"
        diff = subprocess.run(["git","diff","--no-ext-diff"],cwd=manifest["workspace"],
                              capture_output=True,text=True,encoding="utf-8",timeout=10)
        (folder / "reports/final.diff").write_text(diff.stdout, encoding="utf-8")
        report = {"run_id":manifest["run_id"],"mode":"scripted_rehearsal",
                  "status":"FAIL" if failure else "PASS","failure":failure,
                  "elapsed_seconds":round(time.monotonic()-started,2),
                  "real_agent_sessions":0,"real_github_writes":0,"model_cost_usd":0,
                  "closed_issues":sum(i["state"] == "CLOSED" for i in snapshot["issues"].values()),
                  "scenarios":scenarios,"not_validated":["model reasoning","real concurrency","long-duration operation","live budget metering"]}
        write(folder / "reports/summary.json", report)
        summary = (f"# {manifest['run_id']}: {report['status']}\n\n"
                   "Mode: scripted rehearsal. No real agents or GitHub writes. Reference fixes were scripted.\n\n"
                   f"Closed fixture issues: {report['closed_issues']}/12. Elapsed: {report['elapsed_seconds']}s.\n\n"
                   + "\n".join(f"- {s['id']}: {s['status']} — {s['evidence']}" for s in scenarios)
                   + f"\n\nFailure: {failure or 'none'}\n\nNot validated: " + ", ".join(report["not_validated"]) + "\n")
        (folder / "reports/summary.md").write_text(summary, encoding="utf-8")
        manifest["status"] = "rehearsal_failed" if failure else "rehearsal_complete"
        write(folder / "manifest.json", manifest)
    return report
