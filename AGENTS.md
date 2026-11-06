# AGENTS.md

Instructions for AI coding agents in this repository. `CLAUDE.md` points here.

## What this repository is

A hand-curated registry of state attorneys general's AI actions
(`data/state-ags.yaml`), the Python package that checks it and computes the
board (`src/stateags/`), and the method that defines every figure
(`docs/method.md`). The modelmirror.ai site renders the board and computes
nothing, so any figure the site shows is a field of `board.json`.

## How a change lands

- **Branch and PR.** Never push to `main`. Branch off `main`, open one focused
  PR with a conventional-commit title, and say what changed and why. The
  maintainer approves and merges every PR; never submit an approving review.
- **Registry entries are sourced.** An action cites the AG office's own
  announcement; a roster change cites an official or major-outlet source; an
  uncalled race stays `uncalled`, never guessed. Each PR that adds entries says
  which rule in `docs/method.md` each one meets.
- **The method is versioned.** A change to the 730-day window or the rung
  ladder is a new method name (`ag-ai-ambition-v2`), never an edit to v1. A
  change to the data-center threshold is a change to the rule, in its own PR.
- **The board's shape is a contract with the site.** A change to a field in
  `src/stateags/board.py` regenerates `schemas/board.schema.json`
  (`uv run python -m stateags export-schema`) and needs a matching
  modelmirror.ai PR, linked from both descriptions.
- **Docs describe the current design**, not its history. Issue numbers belong
  in PR descriptions and commit messages only.
- **A check that has to wait becomes a scheduled routine, not an open
  session.** When the only work left is a check due days or weeks out (a
  deploy or rebuild effect, a close after a quiet period), comment on the
  issue what will be checked, when, and the result that closes it; schedule a
  fresh-session routine for that date whose prompt carries the issue, the
  check and the criteria in full, and which comments the result, closes the
  issue when the criteria pass, and otherwise @-mentions the maintainer
  (`modelmirror`); record the routine where the next session looks first (the
  project memory, in a Claude project session); then end the session. The
  routine reads and comments only: it pushes and merges nothing.
- **Identity.** Commits use a no-reply address. No personal or organizational
  email addresses anywhere in the repository.

## Local gate

```bash
uv sync
uv run ruff format --check . && uv run ruff check .
uv run mypy src tests
uv run pytest -q
```

CI runs the same steps (`.github/workflows/ci.yml`). Workflows pin every
action to a full commit SHA; run `actionlint` and `zizmor` before pushing a
workflow change.
