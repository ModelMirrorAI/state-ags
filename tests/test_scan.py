"""The newsroom scan, driven by a scripted stand-in for the Messages API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from stateags import scan
from stateags.registry import load_state_ags

REGISTRY = Path("data/state-ags.yaml")
NEWSROOMS = Path("data/newsrooms.yaml")
TODAY = date(2026, 11, 9)
SINCE = date(2026, 10, 26)


@dataclass
class Block:
    type: str
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    text: str = ""


@dataclass
class Response:
    content: list[Block]
    stop_reason: str


def draft(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "ca-examplebot-investigation",
        "title": "California investigates ExampleBot's companion chatbot",
        "announced": "2026-11-02",
        "kind": "investigation",
        "category": "child-safety",
        "states": ["CA"],
        "lead": "CA",
        "developers": ["ExampleBot"],
        "court": None,
        "docket_number": None,
        "why": "An AI chatbot's outputs to minors are central to the investigation.",
        "sources": ["https://oag.ca.gov/news/press-releases/examplebot"],
        "confidence": "high",
    }
    return {**base, **overrides}


class Scripted:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, responses: list[Response]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Response:
        self.requests.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return Response([Block("text", text="Nothing new.")], "end_turn")


def propose(*drafts: dict[str, Any]) -> Response:
    blocks = [
        Block("tool_use", id=f"t{i}", name="propose_action", input=d) for i, d in enumerate(drafts)
    ]
    return Response(blocks, "tool_use")


def test_newsrooms_cover_every_office() -> None:
    shared, offices = scan.load_newsrooms(NEWSROOMS)
    assert len(offices) == 51
    assert shared


def test_batch_records_drafts_and_searches_only_its_newsrooms() -> None:
    registry = load_state_ags(REGISTRY)
    create = Scripted([propose(draft())])
    found, failures = scan.scan_batch(create, registry, ["CA"], ["oag.ca.gov"], SINCE, TODAY)
    assert [p.id for p in found] == ["ca-examplebot-investigation"]
    assert failures == []
    search = create.requests[0]["tools"][0]
    assert search["allowed_domains"] == ["oag.ca.gov"]
    # The messages list is shared across requests; the tool result is its third turn.
    last = create.requests[1]["messages"][2]["content"][0]
    assert last == {"type": "tool_result", "tool_use_id": "t0", "content": "recorded"}


def test_pause_turn_is_resumed() -> None:
    registry = load_state_ags(REGISTRY)
    create = Scripted([Response([Block("server_tool_use")], "pause_turn"), propose(draft())])
    found, failures = scan.scan_batch(create, registry, ["CA"], ["oag.ca.gov"], SINCE, TODAY)
    assert len(found) == 1 and failures == []
    assert len(create.requests) == 3


def test_refusal_is_a_failure_note() -> None:
    registry = load_state_ags(REGISTRY)
    create = Scripted([Response([], "refusal")])
    found, failures = scan.scan_batch(create, registry, ["CA"], ["oag.ca.gov"], SINCE, TODAY)
    assert found == [] and failures == ["CA: the model declined the batch"]


def test_check_sets_aside_invalid_duplicate_and_known() -> None:
    registry = load_state_ags(REGISTRY)
    known = registry.actions[0]
    drafts = [
        scan.Proposal.model_validate(draft()),
        scan.Proposal.model_validate(draft(id="ca-examplebot-again")),
        scan.Proposal.model_validate(draft(id="ca-bad", kind="suit", sources=["https://x/1"])),
        scan.Proposal.model_validate(draft(id=known.id, sources=["https://x/2"])),
        scan.Proposal.model_validate(draft(id="ca-cat", category="nope", sources=["https://x/3"])),
    ]
    accepted, rejected = scan.check(drafts, registry, TODAY)
    assert [p.id for p in accepted] == ["ca-examplebot-investigation"]
    reasons = [r.reason for r in rejected]
    assert reasons[0] == "its source is already cited"
    assert reasons[1].startswith("invalid:")
    assert reasons[2] == f"id {known.id} is already taken"
    assert reasons[3] == "unknown category nope"


def test_apply_appends_valid_entries_and_body(tmp_path: Path) -> None:
    registry_path = tmp_path / "state-ags.yaml"
    registry_path.write_text(REGISTRY.read_text())
    registry = load_state_ags(registry_path)
    result = scan.scan(
        Scripted([propose(draft())]),
        registry,
        scan.load_newsrooms(NEWSROOMS),
        SINCE,
        TODAY,
        states=["CA"],
    )
    candidates = result.to_json()
    actions = scan.apply(candidates, registry_path)
    assert [a.id for a in actions] == ["ca-examplebot-investigation"]
    after = load_state_ags(registry_path)
    assert after.actions[-1].id == "ca-examplebot-investigation"
    assert after.actions[-1].added == TODAY
    assert len(after.data_centers) == len(registry.data_centers)
    assert "\n  announced: '2026-11-02'\n" in registry_path.read_text()
    body = scan.pr_body(candidates)
    assert "`ca-examplebot-investigation` (high confidence)" in body


def test_apply_with_nothing_leaves_the_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "state-ags.yaml"
    registry_path.write_text(REGISTRY.read_text())
    candidates = {"added": TODAY.isoformat(), "accepted": [], "rejected": [], "failures": []}
    assert scan.apply(candidates, registry_path) == []
    assert registry_path.read_text() == REGISTRY.read_text()


@pytest.mark.parametrize("size", [1, 6, 51])
def test_batches_cover_every_office_once(size: int) -> None:
    _, offices = scan.load_newsrooms(NEWSROOMS)
    chosen = sorted(offices)
    flat = [s for b in scan.batches(chosen, size) for s in b]
    assert flat == chosen
