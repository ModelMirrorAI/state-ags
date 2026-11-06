# State attorneys general and AI litigation: the method

The state-AGs dashboard on modelmirror.ai shows how far each state's attorney
general goes in acting against AI developers, which actions each office is in,
and which states tend to act together. This document defines what it reads and
how each figure is made. The registry is `data/state-ags.yaml`, read and
checked by `src/stateags/registry.py`.

## Why a hand-curated registry

State AGs act against AI developers mostly in state court, through
investigations and settlements that never reach a court, and in multistate
letters and amicus briefs. No docket feed carries that, so the registry is
hand-curated. Each action cites the AG office's own announcement; a filed one
names its court, and its docket number once a source gives one. An action in a
federal case that fedcourtsai's AI watchlist (`config/ai-watchlist.yaml` there)
follows names that case, and the build checks the name against the watchlist.

## The rule

An action is listed when an AI developer, or an AI system's training, outputs
or deployment, is central to it (the same rule fedcourtsai's AI watchlist
uses), and one or more state AG offices took part. The 50 states and the
District of Columbia are covered. An action is added by a PR that cites the
rule, on a dated `added` line; nothing merges without the maintainer. A weekly
newsroom scan has an AI model (Anthropic's Claude) search each office's
newsroom for announcements since the last scan and draft each action it finds;
drafts that fail the registry's checks, or repeat an action or source already
listed, are set aside, and the rest arrive as one PR for the maintainer to read
against the rule. The model drafts; it never decides what is listed.

Each action has one **kind**, and each kind feeds one **track**:

| Kind | What it is | Track |
| --- | --- | --- |
| `letter` | A signed letter or public comment aimed at AI companies | enforcement |
| `amicus` | An amicus brief in a case against an AI developer | enforcement |
| `investigation` | An announced investigation or civil investigative demand | enforcement |
| `settlement` | A settlement or assurance of voluntary compliance reached without suit | enforcement |
| `suit` | A suit against an AI developer, in any court | enforcement |
| `defense` | Defending a state AI law against a developer's challenge | defense |
| `advocacy` | Advocacy to a legislature or agency, not aimed at a developer | context |

Only the enforcement track raises a tier. A defense is litigation with an AI
developer, but the AG did not bring it, so the page lists it beside the tier
rather than in it. Advocacy, such as a letter to Congress about federal
preemption of state AI law, is listed as context only.

## The roster and transitions

`offices` lists every state and DC, how the office is filled (`elected`, or
appointed by the `governor`, the `legislature` or the state supreme `court`),
and its holders in the order they serve, each with a source and a distinct
start day. The first holder is one who served, and only the last may be
pending: a `successor`, elected or appointed and not yet in
office, with the day they take it; or an `uncalled` race, which names no winner
until a major outlet calls it.

Each action is attributed to the office, and through the roster to the holder
in office on the action's date. The map shades the office. A state whose last
holder is pending carries a transition badge naming the outgoing and incoming
AG and the day the change happens. The tier is always the office's: holder
attribution labels each action with who announced it and never changes the
tier, so an incoming AG inherits the office's standing in the window, and the
badge says the record is their predecessor's.

## The ambition measure: `ag-ai-ambition-v1`

An office's **tier** on a day is the highest rung any action reached for it in
the trailing 730 days (the action's `announced` date after the window opens and
on or before the day). The rungs:

| Tier | Label | Reached by |
| --- | --- | --- |
| 0 | None recorded | nothing on the enforcement track in the window |
| 1 | Signals | a `letter` |
| 2 | Joins | an `amicus` brief, or a multistate investigation, settlement or suit another state leads |
| 3 | Investigates | the office's own `investigation` or `settlement`, alone or as the coalition's lead |
| 4 | Sues | the office's own `suit`, alone or as the coalition's lead |

"Own" means the office acted alone or is the action's `lead`; a multistate
investigation, settlement or suit always names its lead, and a filed action
(`amicus`, `suit`, `defense`) always names its court, and its docket number
once a source gives one. A tier is an ordinal ranking: tier 4 is more than tier
3, by no stated amount. Counts by kind are published beside every tier so a
reader can see what it rests on.

**Reading rule.** The tier measures what an office has done in public, as its
own announcements record it. It does not measure merit, outcome or intent, and
an investigation the office has not announced is invisible to it. A tier 0
means none recorded, not none taken.

The 730-day window and the rung ladder together define `ag-ai-ambition-v1`. A
change to either is a new method version with a new name, never an edit to
this one, so a published tier always says which definition produced it.

## Reading aids beside the tier

Two figures sit beside the tier to show how much of it rests on broad
coalitions. Neither changes the tier or the method.

- A **large coalition** is an action at least 30 offices took part in. Each
  office's **small-group tier** is its tier counting only the actions that are
  not large coalitions, so an office whose step comes only from a filing most
  states signed shows a lower small-group tier.
- The **pivot** is the in-window action whose removal lowers the most offices'
  tiers, the newest on a tie. The board names it and gives each lowered
  office's tier without it; it is absent when no single action lowers any tier.

## The coalition figures

The coalition figures read only **multistate** actions, those two or more
offices took part in announced on or before the board's day, across both
tracks and every kind, because co-signing is the signal whatever is signed.
For each pair of offices *i* and *j*:

- **affinity** is the Jaccard index: the multistate actions both took part in,
  over the multistate actions either took part in. It is 0 when neither took
  part in any.
- **participation rate** of *j* is the share of all multistate actions *j* took
  part in.

For a chosen lead office *i*, the **join ranking** orders every other office by
affinity with *i* times its participation rate. It is a ranking from past
co-signing, not a probability that a state will join, and the page says so.
Wherever the join ranking or an affinity is shown, the number of multistate
actions it rests on is shown beside it, because both figures are noisy over a
handful of actions.

A forecast of who signs the next multistate action, pre-registered and scored
like the project's other forecasts, is a later step once the registry holds
enough multistate actions to score it against.

## Large AI data centers

`data_centers` lists each AI data center project of at least 1,000 MW (1 GW)
of stated capacity in a state or DC: its developers, locality, capacity, status
(`announced`, `under-construction`, `operating` or `cancelled`), first
announcement date and source, the developer's or the state's own announcement
where one exists. A campus total counts; a multi-site program's total does not
unless one site reaches the threshold. A state hosting any project that is not
cancelled is marked on the map. The layer is context for reading a state's
AI policy, never part of the tier, and a cancelled project stays on record
unmarked. The threshold is part of the layer's definition: a change to it is a
change to the rule, made in its own PR.

## Technology or privacy unit

An office's `tech_unit` records a standing civil enforcement unit whose remit
is privacy, data or technology: a named unit, section, bureau or team, such as
a privacy unit or a bureau of internet and technology. A general consumer
protection division, a single designated attorney, an identity-theft victim
service, and a criminal cybercrime or child-exploitation unit do not count.
Each unit cites the office's own page or announcement where one exists, or
else a major-outlet report, and gives the year it was created where a source
says. A state with no unit on record is unmarked, which means none found, not
none held. Like the data-center layer, the unit is context for reading an
office's capacity to take on technology companies, never part of the tier.

## What the site reads

`python -m stateags build` writes `board.json`, carrying each office's tier,
counts by kind in the window, small-group tier, transition, data-center projects and technology or privacy unit, every action
with each participating office's holder on its date (none before the first
holder on record) and the rung it reaches for them and whether it is a large coalition, the pivot, and the coalition figures,
all computed here; the site renders it and computes nothing. Its shape is
`schemas/board.schema.json`, exported from `src/stateags/board.py`. A pending
holder whose start day has passed is flagged overdue, so a roster that has
fallen behind shows on the board rather than silently attributing actions to
the wrong AG. An action that names a `watchlist_case` the AI watchlist does not
list is refused, so every case link the site renders resolves. The board is
rebuilt every day, because the window slides and successors take office on set
days with no registry edit, and published on the `board` branch.
