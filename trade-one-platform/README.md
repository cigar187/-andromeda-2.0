# Trade One

Trade One is a read-only, modular sports-intelligence platform with separate
pregame and live pipelines. It never places wagers or stores sportsbook
credentials.

Every replaceable component implements a versioned contract. A model, formula,
sport adapter, calibrator, market model, opportunity grader, repository, or
delivery adapter can be changed through configuration without changing the
pipeline or API.

## Quick start

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m trade_one.cli doctor --config config/trade-one.json
PYTHONPATH=src python -m trade_one.cli pregame --config config/trade-one.json \
  --input examples/pregame_request.json
PYTHONPATH=src python -m trade_one.cli live --config config/trade-one.json \
  --input examples/live_request.json
```

Optional API:

```bash
pip install -e ".[api]"
TRADE_ONE_CONFIG=config/trade-one.json uvicorn trade_one.api:create_app --factory
```

See `docs/ARCHITECTURE.md`, `docs/FORMULA_INTEGRATION.md`, and
`docs/SWAPPING_COMPONENTS.md` before replacing a component.
