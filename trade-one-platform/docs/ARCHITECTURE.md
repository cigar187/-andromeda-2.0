# Modular architecture

## Non-negotiable rule

Pipelines import interfaces and canonical contracts only. They never import a
concrete model library, formula implementation, provider SDK, database client,
or delivery mechanism.

## Separate pipelines

```text
Pregame request
  -> control
  -> sport.pregame
  -> formula.pregame
  -> brain.pregame
  -> market.pregame
  -> calibrator.pregame
  -> grader.pregame
  -> repository + delivery

Live request
  -> control
  -> sport.live
  -> formula.live
  -> brain.live
  -> market.live
  -> calibrator.live
  -> grader.live
  -> repository + delivery
```

The current configuration may point multiple slots to one implementation, but
the slots remain independent. Replacing `brain.live` cannot change the
pregame model. Replacing the control engine cannot change the API contract.

## Stable seams

- Canonical DTOs in `trade_one.contracts`
- Abstract interfaces in `trade_one.interfaces`
- Plugin loading and contract-major validation in `trade_one.registry`
- Composition only in `config/trade-one.json`
- Immutable component lineage in every response
- Formula artifact SHA-256 in every response
- No sportsbook execution endpoints or credentials

## Production adapters still required

This package supplies the modular shell, reference implementations, and swap
tests. The following are intentionally interfaces rather than fabricated live
capabilities:

- licensed sports and odds provider adapters;
- Cloud SQL audit/state repository;
- object-storage raw archive;
- trained CatBoost ground-truth/divergence brain;
- trained AutoGluon opportunity brain;
- fitted route calibrators;
- notification/push delivery;
- sport-specific live state reducers beyond the reference baseball adapter.

Reference models are visibly versioned as reference components and must not be
represented as empirically validated production models.

