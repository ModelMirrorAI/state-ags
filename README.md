# State AGs and AI

How far each US state attorney general goes in acting against AI developers,
which actions each office is in, and which states tend to act together. The
dashboard on [modelmirror.ai](https://modelmirror.ai) renders the board this
repository publishes; it computes nothing itself.

- **Registry:** `data/state-ags.yaml`, hand-curated. The roster of all 50
  states and DC with their attorneys general, every AI action an office took
  part in (letters, amicus briefs, investigations, settlements, suits, defenses
  of state AI laws), and AI data center projects of 1 GW or more. Each entry
  cites its source.
- **Method:** [`docs/method.md`](docs/method.md). The `ag-ai-ambition-v1` tier
  (0 None recorded to 4 Sues, the highest rung in a trailing 730 days), the
  coalition figures, and the data-center layer.
- **Board:** `python -m stateags build` writes `board.json`; its shape is
  [`schemas/board.schema.json`](schemas/board.schema.json). The `board`
  workflow rebuilds it every day and on each merge, and publishes it as the
  only file on the `board` branch, which the site fetches.

## Quick start

```bash
uv sync
uv run python -m stateags build --as-of 2026-11-05     # writes board.json
uv run pytest -q
```

An action that names a federal case passes `--watchlist` a copy of
fedcourtsai's `config/ai-watchlist.yaml`, so every case link resolves.

## Changing the registry

Every addition is a PR that cites the rule in `docs/method.md` and the AG
office's own announcement, on a dated `added` line. Nothing is added
automatically. A tier is an ordinal ranking of what an office has announced in
public, not a measure of merit, outcome or intent.

## License

BSD 3-Clause; see [LICENSE](LICENSE).
