## PR Checklist

Please complete this checklist before requesting review:

- [ ] Tests pass: `pytest -q`
- [ ] Pre-commit hooks pass: `pre-commit run --all-files`
- [ ] Mypy passes: `mypy wikibee` (no untyped defs in touched modules)
- [ ] Docs updated where user-facing behavior changed
- [ ] Type hints and docstrings added for new/changed public functions
- [ ] Backward compatibility maintained (including `extract.py` shim, package exports)
- [ ] Error handling considered (clear messages, typed exceptions)
- [ ] Performance / rate limiting and retries considered for network paths
- [ ] CLI changes reflected in docs and `scripts/smoke_extract.py` still works

## What & Why

Describe the problem this PR solves and why the solution is appropriate.

## How

Briefly outline the approach, key changes, and trade-offs.

## Testing

How did you test this? Include commands/output or screenshots as appropriate.

## Follow-ups

Any follow-up work, tracking issues, or deferred items.
