"""Usage: python -m validation.runner prepare|rehearse|check|seed|preflight."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import json

from .rehearsal import rehearse, load_deputy
from .workspace import prepare, load_run, read, write, check
from .control import Limits


def seed(folder, repository=None, publish=False):
    folder = Path(folder).resolve()
    manifest = load_run(folder)
    if manifest["status"] != "prepared":
        raise ValueError("Use a fresh prepared run for live issues; never publish a rehearsal")
    tasks = read(folder / "tasks.json")
    drafts = []
    for task in tasks:
        command = (f'python "{folder / "checks.py"}" --workspace "{manifest["workspace"]}" '
                   f'--case {task["check"]}')
        body = (f"Validation run: {manifest['run_id']}\n\nOwner: `{task['owner']}`\n\n"
                f"Dependencies (must finish first): {', '.join(task['after']) or 'none'}\n\n"
                f"Read README.md for the exact input/output contract. Work only in `{task['owner']}/`.\n\n"
                f"Acceptance: this command exits 0:\n\n```\n{command}\n```\n\n"
                "Add your own boundary tests in your owned directory. Do not modify the external oracle.\n"
                "No branch changes, commits, push or deployment. Completion requires evidence, not a claim.\n")
        drafts.append(dict(id=task["id"],title=f"[{manifest['run_id']}/{task['id']}] {task['title']}",body=body))
    write(folder / "issue-drafts.json", drafts)
    if not publish:
        return {"status":"drafts_only","count":len(drafts),"path":str(folder / "issue-drafts.json")}
    if not repository or not re.fullmatch(r"[\w.-]+/deputy-validation-[\w.-]+", repository):
        raise ValueError("Publishing requires owner/deputy-validation-<name>, never the real project")
    if manifest["repository"] not in (None, repository):
        raise ValueError("Run already belongs to another repository")
    executable = shutil.which("gh")
    if not executable:
        raise ValueError("gh CLI is not installed")

    def gh(*args, parse=False):
        result = subprocess.run([executable,*args],cwd=manifest["workspace"],capture_output=True,
                                text=True,encoding="utf-8",timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout) if parse else result.stdout.strip()

    repo = gh("repo","view",repository,"--json","nameWithOwner,isPrivate",parse=True)
    if not repo.get("isPrivate") or repo.get("nameWithOwner", "").lower() != repository.lower():
        raise ValueError("Only the named private validation repository is allowed")
    # An explicit origin avoids accidentally falling through to the outer repo.
    origin = subprocess.run(["git","remote","get-url","origin"],cwd=manifest["workspace"],
                            capture_output=True,text=True,encoding="utf-8",timeout=10)
    wanted = f"https://github.com/{repository}.git"
    if origin.returncode == 0 and origin.stdout.strip() != wanted:
        raise ValueError("Unexpected fixture origin")
    if origin.returncode:
        subprocess.run(["git","remote","add","origin",wanted],cwd=manifest["workspace"],check=True,timeout=10)
    existing = gh("issue","list","--repo",repository,"--state","all","--limit","1000",
                  "--json","number,title,body",parse=True)
    expected_titles = {item["title"] for item in drafts}
    if any(item["title"] not in expected_titles for item in existing):
        raise ValueError("Validation repository contains issues from another run")
    module = load_deputy(Path(manifest["package"]) / "bin/deputy")
    for label, value in module.LABELS.items():
        color = value[0] if isinstance(value, (tuple,list)) else "888888"
        gh("label","create",label,"--repo",repository,"--color",color,"--force")
    manifest["repository"] = repository
    mapping = manifest.setdefault("issues", {})
    write(folder / "manifest.json", manifest)
    for draft in drafts:
        matches = [i for i in existing if i["title"] == draft["title"]]
        if len(matches) > 1 or (matches and matches[0]["body"].strip() != draft["body"].strip()):
            raise ValueError(f"Ambiguous existing issue: {draft['id']}")
        if matches:
            number = matches[0]["number"]
        else:
            body_path = folder / "issue-body.md"
            body_path.write_text(draft["body"],encoding="utf-8")
            url = gh("issue","create","--repo",repository,"--title",draft["title"],"--body-file",str(body_path))
            number = int(url.rstrip("/").rsplit("/",1)[-1])
        mapping[draft["id"]] = number
        write(folder / "manifest.json", manifest)
    return {"status":"published","repository":repository,"issues":mapping}


def preflight(folder):
    folder = Path(folder).resolve()
    manifest = load_run(folder)
    Limits(**manifest["limits"])
    blockers = []
    if manifest["mode"] == "scripted_rehearsal":
        blockers.append("Create a fresh run; rehearsal workspaces contain reference answers")
    if not manifest.get("repository") or len(manifest.get("issues", {})) != 12:
        blockers.append("Publish 12 tasks to a dedicated private validation repository")
    for field in ("model", "cost_meter"):
        if not manifest.get(field):
            blockers.append(f"Live run needs a verified {field}")
    for tool in ("gh", "claude"):
        if not shutil.which(tool):
            blockers.append(f"Missing executable: {tool}")
    # This release prepares and rehearses; it must not pretend to run live agents.
    blockers.append("Live launch/observation adapter is not connected; do not use this as an unattended supervisor")
    result = {"status":"NOT_READY","blockers":blockers,"live_sessions_started":0}
    write(folder / "reports/preflight.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    for name in ("prepare", "rehearse"):
        p = sub.add_parser(name)
        p.add_argument("--run-id",required=True)
        p.add_argument("--output-root",type=Path)
    p = sub.add_parser("check")
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--case")
    p = sub.add_parser("seed")
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--repository")
    p.add_argument("--publish",action="store_true",help="Explicitly write to the named private GitHub test repository")
    p = sub.add_parser("preflight")
    p.add_argument("--run",type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("prepare", "rehearse"):
            folder = prepare(args.run_id,args.output_root)
            if args.command == "prepare":
                seed(folder)
                print(folder)
                return 0
            result = rehearse(folder)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            print(f"Report: {folder / 'reports/summary.md'}")
            return 0 if result["status"] == "PASS" else 1
        if args.command == "check":
            return check(args.run,args.case)
        result = (seed(args.run,args.repository,args.publish) if args.command == "seed" else preflight(args.run))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if result["status"] == "NOT_READY" else 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"validation: {exc}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
