"""``python -m stateags``: build the board, or export its schema.

``build`` reads ``data/state-ags.yaml`` and writes ``board.json``. An action may
name a case fedcourtsai's AI watchlist follows; ``--watchlist`` points at that
file (``config/ai-watchlist.yaml`` in fedcourtsai), and a named case it does not
list exits 1, so every case link the site renders resolves. Without
``--watchlist`` a registry that names any case exits 1 too, never silently
unchecked.

``scan`` asks a model to search the AG newsrooms for new AI actions and writes
the drafts that pass the registry's checks to a candidates file; it needs an
Anthropic API key in the environment. ``apply-scan`` appends a candidates
file's drafts to the registry and writes the pull request body. See
``stateags.scan``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

from stateags.board import StateAgsBoard
from stateags.registry import build_board, load_state_ags

DEFAULT_REGISTRY = Path("data/state-ags.yaml")
DEFAULT_SCHEMA = Path("schemas/board.schema.json")
DEFAULT_NEWSROOMS = Path("data/newsrooms.yaml")
#: How far back a scan reads by default: a week, with a week's overlap.
DEFAULT_SCAN_DAYS = 14


def watchlist_case_names(path: Path) -> frozenset[str]:
    """The case names fedcourtsai's AI watchlist lists: every ``cases[].name``."""
    data = yaml.safe_load(path.read_text())
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path}: no cases listed; is this the AI watchlist?")
    return frozenset(str(case["name"]) for case in cases)


def write_json(path: Path, payload: object) -> None:
    """Write sorted, indented JSON with a trailing newline, so a rebuild diffs minimally."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def schema_json() -> dict[str, object]:
    """The board's JSON Schema, as committed in ``schemas/board.schema.json``."""
    return StateAgsBoard.model_json_schema()


def _build(args: argparse.Namespace) -> int:
    day = date.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC).date()
    registry = load_state_ags(args.registry)
    if args.watchlist is not None:
        cases = watchlist_case_names(args.watchlist)
    elif any(action.watchlist_case is not None for action in registry.actions):
        print("an action names a watchlist case: pass --watchlist to check it", file=sys.stderr)
        return 1
    else:
        cases = frozenset()
    try:
        board = build_board(registry, day, cases)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    write_json(args.out, board.model_dump(mode="json"))
    print(
        f"stateags: {len(board.offices)} office(s), {len(board.actions)} action(s), "
        f"{board.coalition.multistate_actions} multistate, {len(board.data_centers)} data "
        f"center(s), as of {day.isoformat()} -> {args.out}"
    )
    return 0


def _export_schema(args: argparse.Namespace) -> int:
    write_json(args.out, schema_json())
    print(f"stateags: schema -> {args.out}")
    return 0


def _scan(args: argparse.Namespace) -> int:
    from anthropic import Anthropic

    from stateags import scan

    today = datetime.now(UTC).date()
    since = date.fromisoformat(args.since) if args.since else today - timedelta(DEFAULT_SCAN_DAYS)
    registry = load_state_ags(args.registry)
    newsrooms = scan.load_newsrooms(args.newsrooms)
    states = [s.strip().upper() for s in args.states.split(",")] if args.states else None
    client = Anthropic()
    result = scan.scan(client.messages.create, registry, newsrooms, since, today, states)
    write_json(args.out, result.to_json())
    print(
        f"stateags: scan since {since.isoformat()}: {len(result.accepted)} draft(s) pass, "
        f"{len(result.rejected)} set aside, {len(result.failures)} batch failure(s) -> {args.out}"
    )
    return 1 if result.failures and not result.accepted else 0


def _apply_scan(args: argparse.Namespace) -> int:
    from stateags import scan

    candidates = scan.read_candidates(args.candidates)
    actions = scan.apply(candidates, args.registry)
    load_state_ags(args.registry)
    args.body.parent.mkdir(parents=True, exist_ok=True)
    args.body.write_text(scan.pr_body(candidates))
    print(f"stateags: {len(actions)} action(s) appended to {args.registry}; body -> {args.body}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stateags", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Write board.json from the registry.")
    build.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    build.add_argument("--watchlist", type=Path, help="fedcourtsai's config/ai-watchlist.yaml.")
    build.add_argument(
        "--as-of", help="The day tiers are read on (YYYY-MM-DD; default today, UTC)."
    )
    build.add_argument("--out", type=Path, default=Path("board.json"))
    build.set_defaults(run=_build)
    export = commands.add_parser("export-schema", help="Write the board's JSON Schema.")
    export.add_argument("--out", type=Path, default=DEFAULT_SCHEMA)
    export.set_defaults(run=_export_schema)
    scan_cmd = commands.add_parser("scan", help="Draft new actions from the AG newsrooms.")
    scan_cmd.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    scan_cmd.add_argument("--newsrooms", type=Path, default=DEFAULT_NEWSROOMS)
    scan_cmd.add_argument(
        "--since",
        help=f"Earliest announcement date (YYYY-MM-DD; default {DEFAULT_SCAN_DAYS} days ago).",
    )
    scan_cmd.add_argument("--states", help="Comma-separated postal codes (default all 51).")
    scan_cmd.add_argument("--out", type=Path, default=Path("scan/candidates.json"))
    scan_cmd.set_defaults(run=_scan)
    apply_cmd = commands.add_parser(
        "apply-scan", help="Append a scan's drafts to the registry and write the PR body."
    )
    apply_cmd.add_argument("candidates", type=Path)
    apply_cmd.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    apply_cmd.add_argument("--body", type=Path, default=Path("scan/pr-body.md"))
    apply_cmd.set_defaults(run=_apply_scan)
    args = parser.parse_args(argv)
    result: int = args.run(args)
    return result
