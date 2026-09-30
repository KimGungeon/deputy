"""Create independent Git repositories, never worktrees of the real project."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "validation"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(args, cwd, **kwargs):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", timeout=30, **kwargs)


def prepare(run_id, output_root=None):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", run_id):
        raise ValueError("run-id must contain only letters, digits, underscore, hyphen")
    parent = Path(output_root or VALIDATION / "runs").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent / run_id
    folder.mkdir()  # Never reuse, overwrite or delete a prior execution.
    project = folder / "workspace"
    shutil.copytree(VALIDATION / "fixture", project,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    package = folder / "deputy-package"
    package.mkdir()
    for name in ("bin", "skills", "settings"):
        shutil.copytree(ROOT / name, package / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # The acceptance oracle is pinned outside the workers' project.
    shutil.copyfile(VALIDATION / "checks.py", folder / "checks.py")
    (folder / "reports").mkdir()
    (folder / "prompts").mkdir()
    (project / ".deputy").mkdir()
    cfg = {"review_timeout_minutes":45,"max_revisions":2,"members":[
        {"name":"lead","role":"coordinator","owns":[],"brief":"Review only; no implementation."},
        {"name":"alpha","role":"builder","owns":["alpha"],"brief":"Normalize CSV; include own tests under alpha."},
        {"name":"beta","role":"builder","owns":["beta"],"brief":"Summary and JSON; include own tests under beta."}]}
    write(project / ".deputy/deputy.json", cfg)
    (project / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    (project / ".claude").mkdir()
    # Do not copy a user's credentials/global settings or mutate their defaults.
    write(project / ".claude/settings.json", {"permissions":{"deny":[
        "Bash(git push*)", "Bash(git checkout*)", "Bash(git reset*)",
        "Bash(git rebase*)", "Bash(git commit*)", "Bash(gh release*)", "Bash(gh secret*)"]}})
    for args in (["git","init","-q","--initial-branch=validation"],
                 ["git","add","."],
                 ["git","-c","user.name=Deputy Validation","-c","user.email=validation@example.invalid",
                  "-c","commit.gpgsign=false","commit","-qm","Initial unfinished validation fixture"]):
        result = run(args, project)
        if result.returncode:
            raise RuntimeError(result.stderr)
    tasks = read(VALIDATION / "scenarios/tasks.json")
    write(folder / "tasks.json", tasks)
    write(folder / "faults.json", read(VALIDATION / "scenarios/faults.json"))
    for member in cfg["members"]:
        prompt = (f"You are deputy member {member['name']}. {member['brief']}\n"
                  f"Owned directories: {member['owns']}. Read README.md first.\n"
                  "Run deputy next before every turn. Implement only seeded issues. Review with evidence.\n"
                  "Acknowledge human instructions only after applying them using deputy ack.\n"
                  "Never edit files outside owned directories or switch branches, commit, push or deploy.\n"
                  "Do not modify the acceptance oracle or create new issues without the run coordinator.\n"
                  "/goal Seeded work is complete and no assigned issues remain. Stop after 60 turns.\n")
        (folder / "prompts" / (member["name"] + ".txt")).write_text(prompt, encoding="utf-8")
    manifest = {
        "schema":1,"run_id":run_id,"status":"prepared","mode":"not_started",
        "created_at":datetime.now(timezone.utc).isoformat(),
        "workspace":str(project.resolve()),"package":str(package.resolve()),
        "source_commit":run(["git","rev-parse","HEAD"], ROOT).stdout.strip(),
        "deputy_sha256":hashlib.sha256((package / "bin/deputy").read_bytes()).hexdigest(),
        "fixture_commit":run(["git","rev-parse","HEAD"], project).stdout.strip(),
        "python":sys.executable,"members":[m["name"] for m in cfg["members"]],
        "repository":None,"sessions":{},"model":None,"cost_meter":None,
        "limits":{"seconds":1800,"cost_usd":20,"per_member_restarts":2,"total_restarts":4}}
    write(folder / "manifest.json", manifest)
    return folder


def load_run(folder):
    folder = Path(folder).resolve()
    manifest = read(folder / "manifest.json")
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported run manifest")
    # Refuse manifests redirected at the real repo or another run.
    for key, name in (("workspace", "workspace"), ("package", "deputy-package")):
        if Path(manifest[key]).resolve() != folder / name:
            raise ValueError(f"Invalid {key} path in manifest")
    if not (folder / "workspace/.git").is_dir():
        raise ValueError("An independent fixture Git repository is required")
    actual = hashlib.sha256((folder / "deputy-package/bin/deputy").read_bytes()).hexdigest()
    if actual != manifest["deputy_sha256"]:
        raise ValueError("Pinned deputy was modified")
    return manifest


def check(folder, case=None, label="acceptance"):
    folder = Path(folder).resolve()
    manifest = load_run(folder)
    args = [manifest["python"], "-X", "utf8", str(folder / "checks.py"), "--workspace", manifest["workspace"]]
    if case:
        args += ["--case", case]
    result = run(args, manifest["workspace"])
    (folder / "reports" / (label + ".txt")).write_text(result.stdout + result.stderr, encoding="utf-8")
    return result.returncode
