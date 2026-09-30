# Validation fixture and runner

This directory contains a disposable miniature project for testing deputy's
workflow. It is deliberately separate from the real repository's code and
GitHub issues.

Prepare a new run (the command never reuses or overwrites a run):

```text
python -m validation.runner prepare --run-id smoke-01
```

This creates `validation/runs/smoke-01/` (ignored by Git), an independent Git
repository, an unfinished CSV fixture, an external acceptance oracle, task
drafts, a pinned copy of `bin/deputy`, prompts, and a manifest. The acceptance
oracle is outside the fixture so workers cannot make tests pass by editing it.

Run the local rehearsal:

```text
python -m validation.runner rehearse --run-id smoke-02
```

The rehearsal applies scripted reference answers through a fake service and
replays the deputy command boundary. It checks instruction acknowledgement,
claim ownership, launch failure, project isolation, close failure, discovery
failure, bounded completion, and all 12 independent acceptance cases. It does
not use real Claude sessions, GitHub, model inference, concurrency, or cost.

Draft issues for inspection with `seed`; publishing requires an explicitly named
private repository whose name starts with `deputy-validation-`:

```text
python -m validation.runner seed --run validation/runs/live-01
python -m validation.runner seed --run validation/runs/live-01 \
  --repository OWNER/deputy-validation-20260930 --publish
```

Publishing is guarded against the real `deputy` repository, an unexpected
origin, foreign existing issues, and duplicate or changed task bodies. It does
not start agents. `preflight` deliberately reports `NOT_READY` until a live
session/observation adapter and verified model/cost meter are supplied:

```text
python -m validation.runner preflight --run validation/runs/live-01
```

A rehearsal report explicitly separates synthetic results from the live claims
still unvalidated. Do not call a run an unattended-operation pass based on the
rehearsal alone.

For a published private validation repository, `live-launch` is still dry-run
by default. It prints the exact Claude commands and never starts a process:

```text
python -m validation.runner live-launch --run validation/runs/live-01
python -m validation.runner live-observe --run validation/runs/live-01
python -m validation.runner live-stop --run validation/runs/live-01
```

The execution switch is intentionally explicit and remains blocked until the
manifest records `mode: live`, all 12 issue IDs, a model, and a verified cost
meter. Only then would `--execute` start or stop sessions. The adapter resolves
session IDs from exact cwd/name data and refuses to operate on unregistered or
foreign sessions.
