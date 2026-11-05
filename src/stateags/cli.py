"""``python -m stateags``: build the board, or export its schema.

``build`` reads ``data/state-ags.yaml`` and writes ``board.json``. An action may
name a case fedcourtsai's AI watchlist follows; ``--watchlist`` points at that
file (``config/ai-watchlist.yaml`` in fedcourtsai), and a named case it does not
list exits 1, so every case link the site renders resolves. Without
``--watchlist`` a registry that names any case exits 1 too, never silently
unchecked.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from stateags.board import StateAgsBoard
from stateags.registry import build_board, load_state_ags

DEFAULT_REGISTRY = Path("data/state-ags.yaml")
DEFAULT_SCHEMA = Path("schemas/board.schema.json")


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
    args = parser.parse_args(argv)
    result: int = args.run(args)
    return result
