"""Guarded adapter for a real validation run.

This module never selects sessions by name alone. It is deliberately separate
from the scripted fake boundary and defaults to a dry-run at the CLI layer.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

from .workspace import load_run, read, write


def claude_executable():
    """Prefer Windows command shims over PowerShell scripts under restricted policy."""
    for name in ("claude.cmd", "claude.exe", "claude"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("claude CLI is not on PATH")


def require_live_manifest(folder):
    folder = Path(folder).resolve()
    manifest = load_run(folder)
    blockers = []
    if manifest.get("mode") != "live":
        blockers.append("manifest mode must be live")
    if not manifest.get("repository") or not manifest.get("issues") or len(manifest["issues"]) != 12:
        blockers.append("12 published validation issues are required")
    if not manifest.get("model"):
        blockers.append("model must be recorded")
    if not manifest.get("cost_meter"):
        blockers.append("cost_meter must be verified")
    if blockers:
        raise RuntimeError("live run blocked: " + "; ".join(blockers))
    return folder, manifest


def _run(folder, args, timeout=45):
    manifest = load_run(folder)
    return subprocess.run(args, cwd=manifest["workspace"], capture_output=True,
                          text=True, encoding="utf-8", timeout=timeout)


def observe(folder):
    """Read only exact-project sessions and return a stable snapshot."""
    folder, manifest = require_live_manifest(folder)
    exe = claude_executable()
    result = _run(folder, [exe, "agents", "--json", "--cwd", manifest["workspace"]])
    if result.returncode:
        raise RuntimeError("claude agents failed: " + result.stderr.strip())
    try:
        payload = json.loads(result.stdout)
        rows = payload if isinstance(payload, list) else payload.get("agents", payload.get("sessions"))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("invalid agents response")
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise RuntimeError("invalid claude agents response") from exc
    wanted = set(manifest.get("sessions", {}).values())
    snapshots = []
    for row in rows:
        cwd = row.get("cwd")
        sid = row.get("sessionId") or row.get("id")
        if os.path.normcase(os.path.realpath(cwd or "")) != os.path.normcase(os.path.realpath(manifest["workspace"])):
            continue
        if sid not in wanted:
            continue
        snapshots.append({"id":sid,"name":row.get("name"),"cwd":cwd,
                          "status":row.get("status") or row.get("state"),
                          "startedAt":row.get("startedAt"),"tokens":row.get("tokens")})
    return snapshots


def launch(folder, *, dry_run=True):
    """Launch only the configured members; return commands or session snapshots."""
    folder, manifest = require_live_manifest(folder)
    exe = claude_executable()
    commands = []
    for member in manifest["members"]:
        prompt_path = folder / "prompts" / f"{member}.txt"
        if not prompt_path.is_file():
            raise RuntimeError(f"missing prompt for {member}")
        commands.append([exe, "--bg", "--name", f"deputy-{member}", str(prompt_path)])
    if dry_run:
        return {"mode":"dry-run","workspace":manifest["workspace"],"commands":commands}
    if manifest.get("sessions"):
        raise RuntimeError("sessions already recorded; refuse duplicate launch")
    launched = {}
    for member, command in zip(manifest["members"], commands):
        env = dict(os.environ, DEPUTY_MEMBER=member)
        result = subprocess.run(command, cwd=manifest["workspace"], env=env,
                                capture_output=True, text=True, encoding="utf-8", timeout=180)
        if result.returncode:
            raise RuntimeError(f"launch failed for {member}: {result.stderr.strip()}")
    # Resolve IDs from the exact cwd and expected names after all launches.
    snapshots = observe(folder)
    by_name = {row.get("name"): row["id"] for row in snapshots}
    missing = [m for m in manifest["members"] if by_name.get(f"deputy-{m}") is None]
    if missing:
        raise RuntimeError("launched but could not verify sessions: " + ", ".join(missing))
    manifest["sessions"] = {m:by_name[f"deputy-{m}"] for m in manifest["members"]}
    write(folder / "manifest.json", manifest)
    return {"mode":"live","sessions":manifest["sessions"],"started_at":datetime.now(timezone.utc).isoformat()}


def stop(folder, *, dry_run=True):
    folder, manifest = require_live_manifest(folder)
    exe = claude_executable()
    commands = [[exe,"stop",sid] for sid in manifest.get("sessions", {}).values()]
    if dry_run:
        return {"mode":"dry-run","commands":commands}
    for command in commands:
        result = subprocess.run(command, cwd=manifest["workspace"], capture_output=True,
                                text=True, encoding="utf-8", timeout=45)
        if result.returncode:
            raise RuntimeError(f"stop failed for {command[-1]}: {result.stderr.strip()}")
    return {"mode":"live","stopped":list(manifest.get("sessions", {}).values())}
