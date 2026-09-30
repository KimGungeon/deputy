"""Explicit local service boundary. No network, real gh, or real Claude fallback.

State is deliberately single-writer; parallel race timing is not simulated.
"""
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone


def option(args, key, default=None):
    return args[args.index(key) + 1] if key in args else default


def add_comment(state, issue, body):
    state["sequence"] += 1
    issue["comments"].append({
        "id": f"FAKE_{state['sequence']}", "body": body,
        "createdAt": (datetime.fromisoformat(state["epoch"]) +
                      timedelta(seconds=state["sequence"])).isoformat()})


def dispatch(state, service, args):
    faults = state["faults"]
    key = ("close" if service == "gh" and args[:2] == ["issue", "close"] else
           "query" if service == "claude" and args[:1] == ["agents"] else
           "launch" if service == "claude" and "--bg" in args else None)
    if key and faults.get(key, 0):
        faults[key] -= 1
        return 42, f"injected {key} failure"
    if service == "claude":
        if args[:1] == ["agents"]:
            # Return all rows deliberately: deputy must still filter cwd itself.
            return 0, state["sessions"]
        if "--bg" in args:
            name = option(args, "--name")
            ident = f"session-{len(state['sessions']) + 1}"
            state["sessions"].append(dict(id=ident, sessionId=ident, name=name,
                                          cwd=state["workspace"], status="busy", startedAt=1))
            return 0, ident
        if args[:1] in (["stop"], ["rm"]):
            for row in state["sessions"]:
                if row["id"] == args[1]:
                    row["status"] = "stopped"
                    return 0, ""
            return 1, "unknown session"
    if service == "gh":
        if args[:2] == ["auth", "status"]:
            return 0, "fake authenticated"
        if args[:2] == ["repo", "view"]:
            return 0, {"name": "fake-validation"}
        if args[:2] == ["label", "list"]:
            return 0, [{"name": label} for label in state["labels"]]
        if args[:2] == ["issue", "list"]:
            wanted = option(args, "--state", "open").upper()
            label = option(args, "--label")
            rows = [i for i in state["issues"].values() if i["state"] == wanted]
            if label:
                rows = [i for i in rows if label in {l["name"] for l in i["labels"]}]
            return 0, rows
        if args[:2] == ["issue", "create"]:
            num = str(max(map(int, state["issues"]), default=0) + 1)
            state["issues"][num] = dict(number=int(num), title=option(args, "--title"),
                body=option(args, "--body", ""), state="OPEN", comments=[], labels=[],
                assignees=[], url=f"https://example.invalid/issues/{num}")
            return 0, state["issues"][num]["url"]
        if args[:1] == ["issue"] and len(args) > 2:
            issue = state["issues"].get(args[2])
            if issue is None:
                return 1, "unknown issue"
            if args[1] == "view":
                return 0, issue
            if args[1] == "comment":
                add_comment(state, issue, option(args, "--body"))
                return 0, "fake comment recorded"
            if args[1] == "close":
                issue["state"] = "CLOSED"
                return 0, ""
            if args[1] == "edit":
                labels = {l["name"] for l in issue["labels"]}
                for index, value in enumerate(args):
                    if value == "--add-label":
                        labels.add(args[index + 1])
                    if value == "--remove-label":
                        labels.discard(args[index + 1])
                issue["labels"] = [{"name": label} for label in sorted(labels)]
                if "--add-assignee" in args:
                    issue["assignees"] = [{"login": "fake-account"}]
                if "--remove-assignee" in args:
                    issue["assignees"] = []
                return 0, ""
    return 2, f"Unsupported fake command: {service} {args}"


def main():
    path, service, *args = sys.argv[1:]
    path = Path(path)
    state = json.loads(path.read_text(encoding="utf-8"))
    code, result = dispatch(state, service, args)
    state["calls"].append({"service":service, "args":args, "returncode":code})
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    # The fake output is always UTF-8, independent of the host console locale.
    output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    sys.stdout.buffer.write(output.encode("utf-8"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
