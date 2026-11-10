# Repository Instructions

## Changes and Verification

Keep changes scoped to the user's request. Preserve unrelated work and never
commit credentials, sessions, downloaded evidence, or local command scripts.

Add regression tests for bug fixes and tests for new behavior. Run the relevant
tests and the full suite when feasible:

```bash
venv/bin/python -m unittest discover -s tests
git diff --check
```

## Commits

After each completed and tested change or implementation, create a Git commit.
Each commit must have a concise title and a descriptive body, both written in
English. Explain what changed and why in the body.

Stage only files relevant to that change. Do not include unrelated user changes
or untracked files. Do not amend commits or push to a remote unless explicitly
requested. If verification cannot be completed, report that limitation rather
than claiming the change was tested.
