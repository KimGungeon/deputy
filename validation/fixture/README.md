# Deputy validation fixture

This intentionally unfinished CSV summary tool is an experimental workload, not
production code. Use only the issues created for this run.

- alpha owns `alpha/` (normalization and duplicate handling).
- beta owns `beta/` (summaries and JSON output).
- lead reviews proposals, dependencies, and acceptance evidence; no code changes.
- The CSV header is exactly `name,count`. Data rows contain exactly two fields.
  Ignore completely blank rows. Reject invalid headers, missing/extra fields,
  empty names, negative counts, decimal fractions and non-ASCII digits.
- Rows are dictionaries with `name` and `count` keys. Inputs must not be mutated.

Write your own tests inside your owned directory. Acceptance checks live outside
this working copy and cannot be edited by fixture changes. Do not change branches,
commit, push, deploy, or create work outside the seeded task list. Record new
discoveries as evidence for the coordinator. Stop when assigned work is complete.

The harness creates a separate `.git`, `.deputy` config and `.claude` settings for
each execution copy. Do not run deputy in the template directory.
