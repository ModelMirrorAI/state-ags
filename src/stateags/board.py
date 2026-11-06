"""The published board's shape: what ``board.json`` carries, field by field.

The site reads this file and computes nothing, so every figure it shows is a
field here. ``schemas/board.schema.json`` is exported from :class:`StateAgsBoard`
and checked against it by the tests.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The board's format version; a change to a field's meaning bumps it.
SCHEMA_VERSION: Literal["1.2"] = "1.2"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class StateAgHolderRow(_Strict):
    """One attorney general as the state-AGs board publishes them."""

    name: str | None = Field(description="The holder's name; empty only for an uncalled race.")
    party: str | None = Field(description="The holder's party, as the roster records it.")
    status: Literal["serving", "successor", "uncalled"] = Field(
        description="Where the holder stands: in office, next in office, or a race not called."
    )
    start: date = Field(description="The day the holder took, or takes, the office.")
    sources: list[str] = Field(min_length=1, description="Where the roster's facts come from.")


class StateAgTechUnitRow(_Strict):
    """An office's standing technology or privacy enforcement unit, as the registry records it."""

    name: str = Field(description="The unit's name in the office.")
    established: int | None = Field(description="The year it was created, where a source says.")
    sources: list[str] = Field(min_length=1, description="Where the unit is evidenced.")


class StateAgOfficeRow(_Strict):
    """One office's line on the state-AGs board: who holds it, its tier, and its actions."""

    state: str = Field(description="The two-letter postal code (DC for the District).")
    selection: Literal["elected", "governor", "legislature", "court"] = Field(
        description="How the office is filled."
    )
    holder: StateAgHolderRow | None = Field(
        description="The holder in office on the board's day; none before the first on record."
    )
    transition: StateAgHolderRow | None = Field(
        description="The pending successor or uncalled race, when the office is changing hands."
    )
    transition_overdue: bool = Field(
        description="A pending holder whose start day has passed: the roster needs updating."
    )
    tier: int = Field(ge=0, le=4, description="The office's ag-ai-ambition-v1 tier on the day.")
    tier_label: str = Field(description="The tier's label (None recorded … Sues).")
    tier_small_group: int = Field(
        ge=0,
        le=4,
        description="The tier counting only actions short of a large coalition: what the "
        "office reached alone or with a small group.",
    )
    window_counts: dict[str, int] = Field(
        description="Actions in the window the office took part in, by kind, every kind present."
    )
    action_ids: list[str] = Field(
        description="Every recorded action the office took part in, newest first, in or out "
        "of the window."
    )
    data_center_ids: list[str] = Field(
        description="The state's large AI data center projects that mark it (every status but "
        "cancelled), largest first. Context beside the tier, never part of it."
    )
    tech_unit: StateAgTechUnitRow | None = Field(
        description="The office's standing technology or privacy enforcement unit; none when "
        "the registry records none. Context beside the tier, never part of it."
    )


class StateAgActionRow(_Strict):
    """One recorded action as the state-AGs board publishes it."""

    id: str = Field(description="The action's slug.")
    title: str
    announced: date = Field(description="The day the action was announced.")
    kind: str = Field(description="letter, amicus, investigation, settlement, suit, defense …")
    track: Literal["enforcement", "defense", "context"] = Field(
        description="Which part of the method the kind feeds; only enforcement raises a tier."
    )
    category: str = Field(description="The subject, from the registry's vocabulary.")
    states: list[str] = Field(min_length=1, description="Every office that took part.")
    lead: str | None = Field(description="The office that led, where one did.")
    holders: dict[str, str | None] = Field(
        description="Each participating office's holder on the announced day, by state."
    )
    rungs: dict[str, int] = Field(description="The tier this action reaches for each office.")
    in_window: bool = Field(description="Whether the action counts toward tiers on the day.")
    large_coalition: bool = Field(
        description="Whether at least large_coalition_offices offices took part."
    )
    developers: list[str] = Field(
        description="The AI developers the action is aimed at; empty only for advocacy."
    )
    court: str | None = None
    docket_number: str | None = None
    watchlist_case: str | None = Field(
        default=None, description="The AI watchlist case the action is in, when it is one."
    )
    why: str
    sources: list[str] = Field(min_length=1)


class StateAgDataCenterRow(_Strict):
    """One large AI data center project as the state-AGs board publishes it."""

    id: str
    name: str
    state: str
    locality: str
    developers: list[str] = Field(min_length=1)
    capacity_mw: int = Field(description="The stated capacity, in megawatts.")
    status: Literal["announced", "under-construction", "operating", "cancelled"]
    announced: date = Field(description="The day the project was first announced.")
    sources: list[str] = Field(min_length=1)


class StateAgPair(_Strict):
    """Two offices' co-participation in multistate actions."""

    a: str
    b: str
    joint: int = Field(ge=1, description="Multistate actions both took part in.")
    either: int = Field(ge=1, description="Multistate actions either took part in.")
    affinity: float = Field(ge=0, le=1, description="joint / either (the Jaccard index).")


class StateAgJoin(_Strict):
    """One office's place in a lead office's join ranking."""

    state: str
    affinity: float = Field(ge=0, le=1)
    joint: int = Field(ge=1, description="Multistate actions the lead and this office both joined.")
    either: int = Field(ge=1, description="Multistate actions either took part in.")
    participation: float = Field(ge=0, le=1)
    score: float = Field(
        ge=0, le=1, description="affinity times participation; a ranking, not a probability."
    )


class StateAgCoalition(_Strict):
    """The coalition figures, over every multistate action on record."""

    multistate_actions: int = Field(
        ge=0,
        description="The multistate actions announced on or before the board's day that every "
        "figure here rests on; read it beside them.",
    )
    participation: dict[str, float] = Field(
        description="Each jurisdiction's share of the multistate actions, all 51 present."
    )
    pairs: list[StateAgPair] = Field(
        description="Every pair that co-signed at least once, highest affinity first."
    )
    join_rankings: dict[str, list[StateAgJoin]] = Field(
        description="For each office that took part in a multistate action, the others with a "
        "non-zero score, highest first."
    )


class StateAgPivot(_Strict):
    """The in-window action that alone sets the most offices' tiers, and the tiers without it."""

    action_id: str
    title: str
    offices: dict[str, int] = Field(
        description="Each office whose tier would fall without this action, and that lower tier."
    )
    dropped: int = Field(ge=1, description="How many offices' tiers rest on this action alone.")


class StateAgsBoard(_Strict):
    """``board.json``: the state-AGs dashboard's tiers, actions, data centers and coalitions.

    Written by ``python -m stateags build`` from ``data/state-ags.yaml``; the
    method is ``docs/method.md``. The site renders it and computes nothing.
    """

    schema_version: Literal["1.2"] = SCHEMA_VERSION
    method: Literal["ag-ai-ambition-v1"] = Field(description="The ambition measure's name.")
    as_of: date = Field(description="The day the tiers and transitions are read on.")
    window_days: int = Field(gt=0, description="The trailing window an action counts in.")
    offices: list[StateAgOfficeRow] = Field(description="Every office, by postal code.")
    actions: list[StateAgActionRow] = Field(description="Every recorded action, newest first.")
    defense_and_context: int = Field(
        ge=0, description="Recorded actions off the enforcement track, which raise no tier."
    )
    data_center_threshold_mw: int = Field(
        gt=0, description="The smallest project, in megawatts, the data-center layer lists."
    )
    data_centers: list[StateAgDataCenterRow] = Field(
        description="Every listed project, by state, then largest first, then id."
    )
    coalition: StateAgCoalition
    large_coalition_offices: int = Field(
        gt=1, description="The fewest offices an action needs to count as a large coalition."
    )
    pivot: StateAgPivot | None = Field(
        description="The in-window action whose removal lowers the most offices' tiers; none "
        "when no action alone sets any office's tier."
    )
