"""The weekly newsroom scan: a model reads AG newsrooms and drafts registry entries.

``scan`` asks Claude, a batch of offices at a time, to search those offices'
newsrooms for AI actions announced since a given day, and to draft each one it
finds as a registry action through the ``propose_action`` tool. Every draft is
then checked here: it must validate as an :class:`~stateags.registry.Action`,
cite a source the registry does not already cite, and carry an id not already
taken. The scan writes the drafts that pass, and the reasons the rest failed, to
a candidates file; it never edits the registry.

``apply`` appends the passing drafts from a candidates file to the registry and
writes the pull request body, so the maintainer reads every draft, its source
and the model's reasoning before anything merges. Nothing in this module decides
what is listed: the model proposes, the registry's own checks reject what breaks
the rule's shape, and the maintainer decides the rest.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from stateags.registry import JURISDICTIONS, Action, StateAgRegistry

#: The model that reads the newsrooms; the scan's cost scales with it.
MODEL = "claude-opus-5-5"
#: Offices per request: each batch searches only its offices' newsrooms.
BATCH_SIZE = 6
#: Searches one batch may run.
MAX_SEARCHES = 20
#: Round trips per batch before the scan gives up on it and records why.
MAX_TURNS = 12

PROPOSE_TOOL: dict[str, Any] = {
    "name": "propose_action",
    "description": (
        "Record one AI action by one or more state attorney general offices that you found in "
        "an office's own announcement and that meets the rule. Call it once per action. Do not "
        "call it for an action already on the registry list you were given."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "id",
            "title",
            "announced",
            "kind",
            "category",
            "states",
            "lead",
            "developers",
            "court",
            "docket_number",
            "why",
            "sources",
            "confidence",
        ],
        "properties": {
            "id": {
                "type": "string",
                "description": "Lower-case kebab-case id: the leading state or 'multistate', "
                "the developer, and a word for the action, e.g. 'tx-meta-ai-studio-investigation'.",
            },
            "title": {"type": "string", "description": "One plain-English line."},
            "announced": {"type": "string", "description": "The announcement date, YYYY-MM-DD."},
            "kind": {
                "type": "string",
                "enum": [
                    "letter",
                    "amicus",
                    "investigation",
                    "settlement",
                    "suit",
                    "defense",
                    "advocacy",
                ],
            },
            "category": {
                "type": "string",
                "description": "One key from the registry's category list.",
            },
            "states": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Postal code of every participating office (50 states and DC).",
            },
            "lead": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "The office that led it; the only office for a single-state "
                "action; null for a multistate letter or amicus with no named lead.",
            },
            "developers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Every AI developer it is aimed at; empty only for advocacy.",
            },
            "court": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "The court, for a filed suit, amicus brief or defense.",
            },
            "docket_number": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "The docket number, only when the source gives one.",
            },
            "why": {
                "type": "string",
                "description": "One or two sentences on why it meets the rule.",
            },
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The office's own announcement URL first, then any others.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How sure you are that it meets the rule and every field is right.",
            },
        },
    },
}

SYSTEM = """\
You keep a registry of state attorneys general's actions against AI developers \
current. You search the newsrooms you are given for announcements on or after \
the start date, and record each qualifying action with the propose_action tool.

The rule: an action is listed when an AI developer, or an AI system's training, \
outputs or deployment, is central to it, and one or more state AG offices took \
part. The 50 states and DC are covered; territories are not, so leave them out \
of `states`. A general consumer-protection or privacy action against a company \
that happens to use AI does not qualify; AI must be central.

Kinds: letter (a signed letter or public comment aimed at AI companies); amicus \
(an amicus brief in a case against an AI developer); investigation (an announced \
investigation or civil investigative demand); settlement (a settlement or \
assurance of voluntary compliance reached without suit); suit (a suit against \
an AI developer, in any court); defense (defending a state AI law against a \
developer's challenge); advocacy (to a legislature or agency, not aimed at a \
developer).

Shape rules the registry enforces: a single-state action is led by that state; \
a multistate investigation, settlement or suit names its lead; an amicus, suit \
or defense names its court; a docket number needs its court; every kind but \
advocacy names at least one developer.

Cite the office's own announcement first. Record only what the announcement \
states; never infer a court, docket number, lead or participating state it does \
not give, and lower the confidence when you are unsure. When the announcement of \
a filed suit omits its court, look for the complaint it links or a news report of \
the filing, take the court from that and cite it as a further source; a suit with \
no court is set aside. If you find nothing new, \
say so and record nothing. Some newsrooms are shared state portals: record only \
the attorney general's own releases."""


class Proposal(BaseModel):
    """One drafted action, as the model returned it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    announced: str
    kind: str
    category: str
    states: list[str]
    lead: str | None
    developers: list[str]
    court: str | None
    docket_number: str | None
    why: str
    sources: list[str]
    confidence: str

    def action(self, added: date) -> Action:
        """The registry action this draft becomes, validated by the registry's own model."""
        fields = self.model_dump(exclude={"confidence"})
        return Action.model_validate({**fields, "added": added.isoformat()})


@dataclass
class Rejected:
    """A draft the checks refused, with the reason the PR body reports."""

    proposal: dict[str, Any]
    reason: str


@dataclass
class ScanResult:
    """What one scan found: drafts that pass the checks, drafts that do not, and failures."""

    since: date
    added: date
    accepted: list[Proposal] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "since": self.since.isoformat(),
            "added": self.added.isoformat(),
            "model": MODEL,
            "accepted": [p.model_dump() for p in self.accepted],
            "rejected": [{"proposal": r.proposal, "reason": r.reason} for r in self.rejected],
            "failures": self.failures,
        }


def load_newsrooms(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """The shared hosts and each office's newsroom hosts; every office must have one."""
    data = yaml.safe_load(path.read_text())
    offices = {str(k): [str(h) for h in v] for k, v in data["offices"].items()}
    missing = sorted(JURISDICTIONS - offices.keys())
    unknown = sorted(offices.keys() - JURISDICTIONS)
    if missing or unknown:
        raise ValueError(f"{path}: missing offices {missing}, unknown offices {unknown}")
    empty = sorted(state for state, hosts in offices.items() if not hosts)
    if empty:
        raise ValueError(f"{path}: offices with no newsroom host {empty}")
    return [str(h) for h in data.get("shared", [])], offices


def batches(states: Sequence[str], size: int = BATCH_SIZE) -> list[list[str]]:
    """The offices, in order, in batches of ``size``."""
    return [list(states[i : i + size]) for i in range(0, len(states), size)]


def known_listing(registry: StateAgRegistry) -> str:
    """The registry's actions as the model sees them: id, date, title and first source."""
    lines = [
        f"- {a.id} ({a.announced.isoformat()}): {a.title} <{a.sources[0]}>"
        for a in sorted(registry.actions, key=lambda a: a.announced)
    ]
    return "\n".join(lines) if lines else "(none)"


def batch_prompt(registry: StateAgRegistry, states: Sequence[str], since: date, today: date) -> str:
    """The user turn for one batch: the offices, the window, the categories and what is known."""
    categories = "\n".join(f"- {k}: {v}" for k, v in registry.categories.items())
    return (
        f"Today is {today.isoformat()}. Search the newsrooms of these attorney general offices "
        f"for AI actions announced on or after {since.isoformat()}: {', '.join(states)}. "
        "Record each qualifying action with propose_action, then stop.\n\n"
        f"Categories (use one key):\n{categories}\n\n"
        f"Already on the registry (do not record these again):\n{known_listing(registry)}"
    )


def check(
    proposals: Iterable[Proposal], registry: StateAgRegistry, added: date
) -> tuple[list[Proposal], list[Rejected]]:
    """Split drafts into those that would enter the registry cleanly and those that would not.

    A draft passes when it validates as an action, names a known category, uses an id
    neither the registry nor an earlier draft holds, and cites a first source the registry
    does not cite and no earlier draft gives as its own first source. A later source an
    earlier draft cites in passing does not set a draft aside, so one release naming
    another state's suit cannot hide that suit.
    """
    taken_ids = {a.id for a in registry.actions}
    cited = {s for a in registry.actions for s in a.sources}
    accepted: list[Proposal] = []
    rejected: list[Rejected] = []
    for proposal in proposals:
        try:
            action = proposal.action(added)
        except ValidationError as exc:
            first = exc.errors()[0]
            rejected.append(Rejected(proposal.model_dump(), f"invalid: {first['msg']}"))
            continue
        if action.category not in registry.categories:
            rejected.append(Rejected(proposal.model_dump(), f"unknown category {action.category}"))
        elif action.id in taken_ids:
            rejected.append(Rejected(proposal.model_dump(), f"id {action.id} is already taken"))
        elif action.sources[0] in cited:
            rejected.append(Rejected(proposal.model_dump(), "its source is already cited"))
        else:
            accepted.append(proposal)
            taken_ids.add(action.id)
            cited.add(action.sources[0])
    return accepted, rejected


#: One Messages API call: keyword arguments in, the response out.
CreateMessage = Callable[..., Any]


def scan_batch(
    create: CreateMessage,
    registry: StateAgRegistry,
    states: Sequence[str],
    hosts: Sequence[str],
    since: date,
    today: date,
) -> tuple[list[Proposal], list[str]]:
    """Run one batch to its end: the drafts the model recorded, and any failure notes."""
    tools: list[dict[str, Any]] = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": MAX_SEARCHES,
            "allowed_domains": list(hosts),
        },
        PROPOSE_TOOL,
    ]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": batch_prompt(registry, states, since, today)}
    ]
    proposals: list[Proposal] = []
    failures: list[str] = []
    label = ",".join(states)
    for _ in range(MAX_TURNS):
        response = create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            tools=tools,
            output_config={"effort": "high"},
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "refusal":
            failures.append(f"{label}: the model declined the batch")
            return proposals, failures
        if response.stop_reason == "pause_turn":
            continue
        calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            if response.stop_reason == "max_tokens":
                failures.append(f"{label}: the response hit max_tokens")
            return proposals, failures
        results: list[dict[str, Any]] = []
        for call in calls:
            if call.name != PROPOSE_TOOL["name"]:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "is_error": True,
                        "content": f"unknown tool {call.name}",
                    }
                )
                continue
            try:
                proposals.append(Proposal.model_validate(call.input))
                text = "recorded"
            except ValidationError as exc:
                text = f"not recorded: {exc.errors()[0]['msg']}"
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": text})
        messages.append({"role": "user", "content": results})
    failures.append(f"{label}: stopped after {MAX_TURNS} turns")
    return proposals, failures


def scan(
    create: CreateMessage,
    registry: StateAgRegistry,
    newsrooms: tuple[list[str], dict[str, list[str]]],
    since: date,
    today: date,
    states: Sequence[str] | None = None,
) -> ScanResult:
    """Scan every office (or ``states``) batch by batch, then check every draft together."""
    shared, offices = newsrooms
    chosen = sorted(states) if states else sorted(offices)
    result = ScanResult(since=since, added=today)
    drafts: list[Proposal] = []
    for batch in batches(chosen):
        hosts = sorted({h for s in batch for h in offices[s]} | set(shared))
        found, failures = scan_batch(create, registry, batch, hosts, since, today)
        drafts.extend(found)
        result.failures.extend(failures)
    result.accepted, result.rejected = check(drafts, registry, today)
    return result


def _action_yaml(action: Action) -> str:
    """One action as a registry list item, in the registry's own field order and quoting."""
    data = action.model_dump(mode="json", exclude_none=True)
    data["announced"] = action.announced.isoformat()
    data["added"] = action.added.isoformat()
    if not data.get("developers"):
        data.pop("developers", None)
    text = yaml.safe_dump([data], sort_keys=False, allow_unicode=True, width=100)
    for key in ("announced", "added"):
        text = text.replace(f"  {key}: {data[key]}\n", f"  {key}: '{data[key]}'\n")
    return text


def apply(candidates: dict[str, Any], registry_path: Path) -> list[Action]:
    """Append the accepted drafts to the registry's actions, before its data centers."""
    added = date.fromisoformat(candidates["added"])
    actions = [Proposal.model_validate(p).action(added) for p in candidates["accepted"]]
    if not actions:
        return []
    text = registry_path.read_text()
    marker = "\ndata_centers:"
    if marker not in text:
        raise ValueError(f"{registry_path}: no data_centers section to insert before")
    block = "".join(_action_yaml(a) for a in actions)
    head, tail = text.split(marker, 1)
    registry_path.write_text(head.rstrip("\n") + "\n" + block.rstrip("\n") + marker + tail)
    return actions


def pr_body(candidates: dict[str, Any]) -> str:
    """The pull request body: every draft with its reasoning, then what was set aside."""
    lines = [
        f"The weekly newsroom scan drafted these registry actions from AG announcements "
        f"on or after {candidates['since']}, using {candidates['model']}. Each passes the "
        "registry's checks; whether it meets the rule in `docs/method.md` is yours to decide. "
        "Delete any entry that does not before merging.",
        "",
    ]
    for p in candidates["accepted"]:
        lines += [
            f"### `{p['id']}` ({p['confidence']} confidence)",
            f"{p['title']}. {p['kind']}, {', '.join(p['states'])}, announced {p['announced']}.",
            "",
            f"{p['why']}",
            "",
            f"Source: {p['sources'][0]}",
            "",
        ]
    if candidates["rejected"]:
        lines += ["### Set aside by the checks", ""]
        for r in candidates["rejected"]:
            title = r["proposal"].get("title", r["proposal"].get("id", "?"))
            source = (r["proposal"].get("sources") or ["no source"])[0]
            lines.append(f"- {title} ({r['reason']}): {source}")
        lines.append("")
    if candidates["failures"]:
        lines += ["### Batches that did not finish", ""]
        lines += [f"- {f}" for f in candidates["failures"]]
        lines.append("")
    return "\n".join(lines)


def read_candidates(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data
