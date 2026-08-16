# Trade One

## Product and technical blueprint

**Status:** architecture baseline  
**Version:** 1.0  
**Date:** 2026-07-28  
**Purpose:** implementation contract for a short-horizon, read-only sports intelligence application  
**Source package reviewed read-only:** `/Users/rac187/Documents/Codex/2026-07-16/build/outputs/Codex Control Engine`
**Project boundary:** Trade One is independent from M-31. It has separate product identity, repository, schemas, models, configuration, deployment, audit data, and roadmap.

---

## 1. Executive decision

Trade One is a live sports-state and market-divergence system. It is not a stock-themed sportsbook, not a charting skin over live odds, and not a claim of sub-second prediction without sub-second licensed feeds and measured infrastructure.

Its primitive is the **decision window**: a bounded interval in a contest during which the system continuously estimates:

1. what is likely to happen in the sport;
2. what the market/public currently prices;
3. whether the calibrated difference remains actionable after vig, spread, fees, slippage, latency, uncertainty, and risk constraints.

The owned three-engine lineage remains, but responsibilities change:

- **Codex Control Engine → Trade One Control:** deterministic ingestion, identity, point-in-time enforcement, text enrichment, and model control plane.
- **CatBoost Formula Engine → State & Divergence Engine:** sport-state distributions, market-state distributions, conditional micro-event probabilities, and residual divergence.
- **AutoGluon Pick Engine → Opportunity & Allocation Engine:** opportunity quality, fill/return estimates, abstention, ranking, and constrained slate/window allocation.
- **Net-new live plane:** event ledger, sport adapters, order-book builder, live state estimator, calibration service, latency accounting, risk service, replay/execution simulator, and live gateway.

The first production sport should be **MLB baseball**, because pitches, plate appearances, half-innings, base/out state, and pitching changes form comparatively crisp event boundaries. Basketball follows once possession reconstruction is reliable. Football follows once drive/play state and clock correction logic are proven. Hockey or other period/shift sports are subsequent adapters, not implied capabilities.

### Go/no-go architecture decisions

| Decision | Baseline |
|---|---|
| Core representation | Append-only event-time ledger plus deterministic materialized live state |
| Prediction contract | Distributions and calibrated probabilities, never a bare pick |
| Two probability layers | `P_sport` and `P_market` are separately modeled and versioned |
| Opportunity | Cost- and uncertainty-adjusted divergence, with explicit abstention |
| Live transport | Provider adapters → durable log → ordered reducers → inference/risk |
| Persistence | Cloud SQL for relational state, audit, configuration, and lineage |
| Raw replay | Immutable/versioned object storage; not Cloud SQL JSON alone |
| Live hot state | In-memory per-event actor/cache rebuilt from ledger |
| Model serving | Owned containers; CPU-serving target after training where practical |
| LLM dependency | None in the hot path; owned encoder/rules for text, optional offline models |
| RL claim | Prohibited until logged actions, propensities, rewards, and valid OPE exist |
| First product mode | Pregame micro-period intelligence, market-release watch, historical replay, and optional paper tracking |

Trade One never places, submits, modifies, cancels, or routes a wager. It holds no sportsbook credentials and has no production execution adapter. The user reads or copies the intelligence and independently acts, if desired, in a separate third-party sportsbook application.

### 1.1 Separation from M-31

Trade One and M-31 are two independent products. They may share lessons or a deliberately extracted generic library later, but they do not share by default:

- repositories or release trains;
- databases, Cloud SQL instances, buckets, or audit ledgers;
- model registries, artifacts, features, or training datasets;
- APIs, credentials, service accounts, or runtime configuration;
- product branding, user interface, roadmaps, or acceptance gates;
- performance claims or validation evidence.

No Trade One decision, schema, or code change modifies M-31. Any future shared component requires an explicit interface, separate versioning, and approval in both projects.

### 1.2 Revised launch thesis: forecast before the derivative market opens

The launch product does not require users to react between live plays. Trade One prepares sport-native micro-period forecasts early in the day, watches for sportsbooks to publish the corresponding markets, and surfaces a copy-ready opportunity as soon as a price can be evaluated.

```text
early-day data collection
    → precompute F3/F5, inning, quarter, and half distributions
    → monitor derivative-market availability
    → map the newly published market to a canonical outcome
    → compare reference price with the prepared distribution
    → publish READY / WATCH / PASS with expiry
    → refresh on lineup, injury, weather, starter, or price changes
```

This shifts the first competitive problem from sub-second live inference to:

- forecast readiness before market publication;
- reliable discovery of newly opened derivative markets;
- exact settlement-rule and market-identity mapping;
- rapid repricing after confirmed pregame information;
- concise delivery while the early line is still available.

Trade One still needs recurring feeds during the day, but not continuous play-by-play for the launch version. Schedules, probable starters, lineups, injuries, weather, market availability, and odds can be refreshed on seconds-to-minutes cadences according to source terms and rate limits.

---

## 2. Product identity and experience

### 2.1 Identity

**Trade One** means one contest, one live state, one bounded opportunity at a time. The experience should feel like a sports command surface: field/court context first, time and transitions second, pricing third.

Avoid candlestick charts, green/red ticker walls, “buy/sell” copy, and generic financial metaphors. Use:

- **Window** — the bounded sports interval.
- **Lean** — a model direction before eligibility.
- **Opportunity** — a direction that passes pricing and risk gates.
- **Enter / reduce / exit** — only when an execution venue actually supports those actions.
- **Pass** — the default when evidence, freshness, liquidity, or calibration is insufficient.
- **State pulse** — the change after a play, pitch, possession, or market update.

### 2.2 Primary screens

#### Live board

Each game card shows:

- sport-native score, clock/inning, possession/base-out/drive state;
- current active window and its closing condition;
- `P_sport`, `P_market`, adjusted opportunity, uncertainty band;
- feed freshness and model age;
- best bid/ask, spread, executable depth, recent trade intensity;
- eligibility state: `WATCH`, `READY`, `PASS`, `HALTED`, or `STALE`;
- one-line evidence codes, never free-form model rationalization.

Default ordering is by **actionable opportunity after risk**, not raw probability.

#### Morning slate and Market Release Watch

The default launch screen is the **Morning Slate**, not the live board. For each scheduled game it shows:

- forecast readiness and missing-information state;
- expected market families: inning 1–5, first three, first five, Q1/Q2/H1, or Q1/Q2/H1 football;
- precomputed outcome distribution and uncertainty;
- probable/confirmed participant status;
- next expected information event;
- market status: `NOT_POSTED`, `DISCOVERED`, `PRICED`, `MOVED`, `SUSPENDED`, or `CLOSED`;
- earliest observed reference line/odds and current reference line/odds;
- whether the first observed price passed the opportunity gate.

When a watched market first appears, Trade One:

1. validates its teams, period, line, side, and settlement semantics;
2. records `first_seen_at` and the complete first observed quote;
3. evaluates it against the already prepared distribution;
4. publishes `READY`, `WATCH`, or `PASS`;
5. sends an optional in-app/push alert;
6. continues repricing until the pregame cutoff or a material state change.

The objective is not merely “early in the day.” It is **model ready before market ready**.

#### Game room

The game room has five coordinated regions:

1. **Sport state:** field/court/drive diagram and current canonical state.
2. **Window rail:** current and next expected boundaries.
3. **Probability split:** sport distribution vs market-implied distribution, including interval/quantiles.
4. **Market depth:** price/depth ladder and liquidity diagnostics without stock-chart decoration.
5. **Audit ribbon:** event version, provider freshness, model/calibrator version, decision ID, and risk reasons.

Every state change is attributable to an event. Selecting a point on the timeline reconstructs exactly what the system knew at that instant.

#### Opportunity card

The card is optimized for rapid reading and manual transfer:

- sportsbook/market label and exact outcome definition;
- observed reference price/odds and timestamp;
- model probability with confidence interval;
- market no-vig probability;
- expected value before and after estimated vig/price movement;
- maximum valid age and expiry boundary;
- optional user-defined tracking amount and limiting risk rule;
- invalidation triggers.

Actions are limited to `COPY`, `PIN`, `TRACK AS PAPER`, and `DISMISS`. `COPY` produces a compact, unambiguous payload such as `MLB — Team A/Team B — First 5 Under 4.5 — reference -110 — valid through first pitch/state change`. It never transmits the selection to a sportsbook.

#### Replay lab

Replay the game and book in event time at 0.25×–20×. Toggle:

- information available as observed vs corrected final feed;
- champion vs challenger;
- zero latency vs measured latency;
- quoted price vs simulated fill;
- text/weather/market feature families;
- calibration and risk policies.

#### Governance console

Expose feed health, unresolved identities, late-arrival rates, calibration drift, model cohorts, promotion results, kill switches, and replay comparison.

### 2.3 User-facing invariants

- Probabilities always carry `as_of`, `model_version`, `calibrator_version`, and freshness.
- “Edge” never means `P_sport - displayed_price` without no-vig and cost adjustment.
- A stale or crossed book is never actionable.
- A corrected play can revise state but never rewrite the original observation.
- The UI distinguishes *forecast confidence* from *market liquidity*.
- No prediction is presented as guaranteed.

---

## 3. Sport-specific decision windows

A window is defined by a start predicate, an end predicate, allowed market families, state transition schema, maximum age, and risk rules. Windows are versioned configuration, not UI-only labels.

### 3.1 Baseball

| Window | Opens | Closes | Primary targets | State |
|---|---|---|---|---|
| Pitch | ready-for-pitch/previous pitch settled | next pitch result or timeout | pitch result where venue supports it | count, bases, outs, batter/pitcher, handedness |
| Plate appearance | batter becomes active | PA completes | PA outcome, reach base, strikeout | count path, matchup, pitch mix, fatigue |
| Half-inning | third out of prior half / inning start | third out | runs in half, next score, team total increment | bases, outs, batting order, bullpen |
| Pitcher stint | pitcher enters | removal/game end | outs, strikeouts, runs allowed | pitch count, times through order, leverage |
| Short run window | configured inning boundary | boundary expires | game/inning totals or side | score, leverage, remaining outs |

MVP supports plate-appearance and half-inning estimates. Pitch-level action is gated until observed p99 feed-to-decision latency, provider timestamp quality, and venue lifecycle can support it. Public “real-time” gamefeeds do not establish tradable sub-second capability.

Model candidates:

- Bayesian run-expectancy state update over base/out/count;
- semi-Markov plate-appearance duration and transition model;
- competing-risks hazards for PA outcomes;
- CatBoost residual specialists conditioned on state;
- particle or ensemble filtering for latent pitcher/batter form.

### 3.2 Basketball

| Window | Opens | Closes | Primary targets | State |
|---|---|---|---|---|
| Possession | controlled possession begins | change of possession / period end | possession points, next score | lineup, ball state, shot clock, foul state |
| Two-possession burst | possession boundary | two completed possessions | short score differential | lineups, pace, timeout/foul context |
| Clock window | configured clock threshold | elapsed game-clock interval | points, margin, total | score, clock, possession, bonuses |
| Quarter | period start | period end | quarter side/total | rotations, fouls, rest, pace |
| Lineup stint | substitution set stabilizes | next material substitution | scoring/pace distribution | ten-player lineup, matchups |

Possession reconstruction must tolerate rebounds, jump balls, reviews, score corrections, and clock edits. A vendor possession flag is evidence, not the canonical truth.

Model candidates:

- hidden semi-Markov possession segmenter;
- conditional point-mass distribution `{0,1,2,3,4+}`;
- lineup random effects plus boosted residuals;
- survival model for possession duration;
- sequential filter for pace and shooting-state uncertainty.

### 3.3 Football

| Window | Opens | Closes | Primary targets | State |
|---|---|---|---|---|
| Play sequence | ready state after prior play | N plays or terminal event | first down, points, turnover | down, distance, yard line, clock, personnel |
| Drive | possession starts | score, punt, turnover, half | drive points/result | field position, timeouts, win context |
| Clock window | configured threshold | time/possession boundary | points before threshold | possession, clock, timeout, two-minute rules |
| Quarter | quarter start | quarter end | quarter side/total | score, field position, possessions |

Reviews, penalties, nullified plays, clock runoff, and stat corrections make revision handling a first-class requirement.

Model candidates:

- Markov/semi-Markov drive transitions;
- competing hazards for score, turnover, punt, downs, half end;
- play-outcome distribution conditional on down/distance/personnel;
- Bayesian drive-strength updates with game and team priors.

### 3.4 Hockey and other period/shift sports

Hockey adapter candidates: shift, power-play, possession-zone sequence, and period. Required state includes manpower, goaltender state, zone, shot sequence, line combinations, and delayed penalties. Shift inference is not considered built until roster-on-ice timing is licensed and validated.

### 3.5 Window lifecycle

```text
SCHEDULED → OPEN → OBSERVING → READY → EXPIRED
                        ↘ PASS
                        ↘ HALTED
```

`READY` requires:

- canonical state at a stable revision;
- eligible market lifecycle;
- synchronized and fresh sport and book data;
- calibrated model coverage for route;
- positive net opportunity;
- all risk gates pass.

Any upstream correction increments the window revision and invalidates earlier decisions if their state hash changes.

---

## 4. Canonical event model

### 4.1 Principles

- Store provider messages exactly once in raw storage by content hash, but process idempotently at least once.
- Separate **event time**, **provider publication time**, **gateway receive time**, and **processing time**.
- Never overwrite corrections. Corrections reference prior provider revisions.
- Assign total order only within a canonical game stream. Cross-game total order is unnecessary.
- A deterministic reducer builds state from the canonical ordered ledger.
- Features declare their availability time and lineage.

### 4.2 `CanonicalSportEvent`

```json
{
  "schema_version": "tradeone.sport_event.v1",
  "event_uid": "t1:mlb:game123:provider:abc:r2",
  "canonical_game_id": "mlb:2026:game123",
  "sport": "baseball",
  "league": "mlb",
  "season": "2026",
  "provider": {
    "name": "licensed_feed_a",
    "record_id": "abc",
    "revision": 2,
    "supersedes_record_id": "abc-r1"
  },
  "event_type": "pitch.result",
  "event_time": "2026-07-28T19:02:14.183Z",
  "provider_published_at": "2026-07-28T19:02:14.420Z",
  "gateway_received_at": "2026-07-28T19:02:14.511Z",
  "processed_at": "2026-07-28T19:02:14.533Z",
  "sequence": {
    "provider_sequence": 1882,
    "canonical_sequence": 431,
    "ordering_key": "mlb:2026:game123"
  },
  "status": "confirmed",
  "participants": {
    "offense_team_id": "team:a",
    "defense_team_id": "team:b",
    "primary_player_id": "player:x",
    "secondary_player_id": "player:y"
  },
  "state_before": {
    "inning": 5,
    "half": "top",
    "outs": 1,
    "balls": 1,
    "strikes": 2,
    "bases_mask": 5,
    "home_score": 2,
    "away_score": 1
  },
  "payload": {
    "result": "single",
    "runs_scored": 1
  },
  "quality": {
    "timestamp_precision_ms": 1,
    "confidence": 1.0,
    "is_late": false,
    "is_correction": true
  },
  "raw_object_uri": "gs://trade-one-raw/...#generation",
  "content_sha256": "...",
  "ingest_trace_id": "..."
}
```

`state_before` is a provider assertion used for reconciliation. The canonical reducer independently derives state and emits a mismatch if they disagree.

### 4.3 Text signal

```json
{
  "schema_version": "tradeone.text_signal.v1",
  "signal_uid": "...",
  "source": "team_official",
  "source_record_id": "...",
  "published_at": "...",
  "first_observed_at": "...",
  "gateway_received_at": "...",
  "language": "en",
  "body_object_uri": "gs://...",
  "entities": [{"canonical_id": "player:x", "confidence": 0.99}],
  "signal_codes": ["INJURY_STATUS_CHANGED"],
  "effective_scope": ["game:...", "player:x"],
  "extractor_version": "owned-text-encoder-3",
  "human_verified": false
}
```

Only timestamped, licensed text is used. Publication time, first observation, and corrections are retained. Text embeddings do not enter training rows before `first_observed_at`.

### 4.4 Weather signal

Include observation/forecast issue time, valid time, station/grid identity, source revision, field geometry, and values such as wind vector, precipitation probability, temperature, humidity, roof state, and air density. Training uses the forecast revision actually available at the decision cutoff, not a final weather observation.

---

## 5. Canonical market and order-book model

### 5.1 Market definition

```json
{
  "schema_version": "tradeone.market.v1",
  "canonical_market_id": "venue:market-id",
  "venue": "venue_a",
  "sport": "baseball",
  "canonical_game_id": "mlb:2026:game123",
  "market_family": "half_inning_runs",
  "outcome_definition": {
    "side": "over",
    "line": 0.5,
    "period": "top_5"
  },
  "contract_type": "binary",
  "tick_size": 0.01,
  "fee_schedule_id": "venue_a:2026-07",
  "settlement_rule_version": "venue_a-rule-17",
  "opens_at": "...",
  "closes_at": "...",
  "status": "open"
}
```

Settlement rules are versioned data. Two apparently identical markets from different venues are not merged unless outcome and void rules are proven equivalent.

### 5.2 `OrderBookEvent`

```json
{
  "schema_version": "tradeone.book_event.v1",
  "book_event_uid": "...",
  "canonical_market_id": "venue:market-id",
  "venue": "venue_a",
  "channel": "orderbook_delta",
  "provider_sequence": 991337,
  "event_time": "...",
  "gateway_received_at": "...",
  "processed_at": "...",
  "operation": "upsert_level",
  "side": "bid",
  "outcome": "yes",
  "price": 0.54,
  "quantity": 125,
  "trade_id": null,
  "snapshot_id": "snap-44",
  "checksum": "...",
  "raw_object_uri": "gs://...",
  "quality": {"gap_detected": false, "is_replay": false}
}
```

### 5.3 Book builder requirements

For every market:

1. load a sequence-anchored snapshot;
2. buffer deltas received during snapshot fetch;
3. apply only contiguous deltas;
4. verify checksum when supported;
5. mark `GAPPED` and resnapshot on discontinuity;
6. expose an atomic immutable view;
7. retain every raw message and reconstructed checkpoint for replay.

Derived features are computed over event-time horizons such as 250 ms, 1 s, 5 s, 30 s, and since-window-open:

- best bid, best ask, midpoint, microprice;
- absolute and relative spread;
- depth at top 1/3/5/10 levels;
- normalized imbalance `(B-A)/(B+A)`;
- order-flow imbalance from depth changes;
- signed trade intensity and volume;
- acceleration of trade count and notional;
- cancel/add ratios;
- realized short-horizon volatility;
- price impact and recovery after trades;
- executable VWAP for proposed quantity;
- book age, gap state, and venue status.

The book is an information source, not truth. Market features feed `P_market` and selected residual features but never overwrite `P_sport`.

### 5.4 Pregame Market Release Watch

Full order-book depth is optional for launch. A sportsbook odds feed may expose only market snapshots. The Market Release Watch normalizes each provider response into:

```json
{
  "canonical_market_key": "mlb:game123:first_5:total:under:4.5",
  "provider": "odds_feed_a",
  "provider_market_id": "...",
  "sportsbook": "book_a",
  "market_family": "first_5_total",
  "period": "first_5",
  "side": "under",
  "line": 4.5,
  "decimal_odds": 1.91,
  "provider_updated_at": "...",
  "first_seen_at": "...",
  "received_at": "...",
  "status": "open",
  "is_first_observation": true,
  "settlement_rule_version": "..."
}
```

Discovery rules:

- Poll or consume provider streams only within licensed rate limits.
- Increase cadence around historically observed market-release windows.
- Use a slower cadence when games are distant and no material information is expected.
- Record every line/price change with `first_seen_at`; never replace the opening observation.
- Require exact canonical mapping before alerting.
- Do not infer that a market is unavailable merely because one sportsbook or aggregator has not published it.
- Treat provider timestamp and Trade One receipt time separately.

Suggested initial cadence, subject to provider limits:

| Time to event | Market/information refresh |
|---|---:|
| More than 12 hours | 10–15 minutes |
| 4–12 hours | 3–5 minutes |
| 1–4 hours | 30–60 seconds |
| Final hour | 10–30 seconds |
| After pregame cutoff | stop for launch routes |

Webhooks or streaming updates are preferable when the provider supports them. Aggressive polling is not a substitute for a licensed feed.

---

## 6. Event time, watermarking, and correction policy

Four clocks must be retained:

- `event_time`: when the sports/market event happened according to source;
- `published_at`: when the provider made it available;
- `received_at`: when Trade One received it;
- `processed_at`: when a component processed it.

### 6.1 Ordering

- Partition by `canonical_game_id` for sport events and `canonical_market_id` for book events.
- Use provider sequence when available.
- Canonical sequence is assigned only after reconciliation.
- Idempotency key is `(provider, record_id, revision)` plus content hash collision detection.
- Consumers must be idempotent because durable messaging may redeliver.

Google Pub/Sub supports within-key ordering but is at-least-once, and ordering has latency/availability tradeoffs. Therefore Pub/Sub delivery order is not the canonical record by itself; reducer sequence and deduplication remain mandatory ([Google Cloud: ordered messages](https://docs.cloud.google.com/pubsub/docs/ordering)).

### 6.2 Watermarks

Maintain independent watermarks by provider and stream:

```text
watermark = max_event_time_seen - route_allowed_lateness
```

Initial allowed-lateness policy:

| Route | Fast path | Reconciliation path |
|---|---:|---:|
| Order-book delta | 250 ms | 5 s |
| Pitch/play event | 1 s | 30 s |
| Basketball possession event | 2 s | 60 s |
| Text signal | 5 s | 10 min |
| Weather | 60 s | 30 min |

These are starting configuration values, not feed claims. They are replaced by empirical per-provider distributions.

Events earlier than the fast watermark:

- are written to the immutable ledger;
- do not silently mutate an emitted decision;
- trigger deterministic state revision;
- generate `decision_invalidation` if a prior state hash changed;
- flow through reconciliation replay;
- count toward provider late-arrival SLOs.

### 6.3 Replayability

Replay input is the immutable raw object generation plus a manifest containing:

- exact object URIs/generations;
- schema registry versions;
- identity-map snapshot;
- reducer and feature code commit;
- event-time/watermark policy;
- model and calibrator artifacts;
- risk/config versions;
- simulated gateway and decision latency.

Cloud Storage objects are immutable during an object generation, and versioning can retain noncurrent generations; lifecycle and soft-delete policy must still be configured deliberately ([Google Cloud: objects](https://docs.cloud.google.com/storage/docs/objects), [object versioning](https://docs.cloud.google.com/storage/docs/object-versioning)).

---

## 7. State topology

```text
Provider feeds
   │
   ├── sport PBP/tracking ──┐
   ├── market books/trades ─┼─> adapters -> raw immutable log
   ├── weather              │                 │
   └── timestamped text ────┘                 v
                                    canonicalization/reconciliation
                                               │
                         ┌─────────────────────┴──────────────────────┐
                         v                                            v
                 per-game state actor                         per-market book actor
                         │                                            │
                         └──────────── feature snapshots ─────────────┘
                                               │
                           Trade One Control / state validation
                                               │
                         ┌─────────────────────┴──────────────────────┐
                         v                                            v
                  Ground-truth state model                     Market-pricing model
                     P_sport(Y|S_t)                              P_market(Y|M_t)
                         └─────────────────────┬──────────────────────┘
                                               v
                                calibration + divergence/costs
                                               │
                                  opportunity grading/allocation
                                               │
                                      risk + abstention gate
                                               │
                               API/UI, alerts, copy, and paper tracker
```

### 7.1 Deterministic state reducer

Every sport adapter implements:

```text
reduce(previous_state, canonical_event) -> new_state, emitted_boundaries, anomalies
```

Requirements:

- pure and deterministic;
- sport rules versioned by league/season;
- state hash at every canonical sequence;
- correction and replay support;
- invariant checks (score monotonicity subject to correction, legal outs/down/clock, participant validity);
- no learned model in the reducer.

### 7.2 Live state actor

One logical actor per game:

- holds current reducer state and rolling feature windows;
- processes canonical sequence serially;
- snapshots periodically to durable storage;
- recovers from the ledger;
- emits `StateSnapshot` after meaningful transitions;
- never treats local memory as authoritative persistence.

For MVP, an owned container worker with consistent sharding is sufficient. A specialized actor framework is optional only after load tests.

---

## 8. Model topology

### 8.1 Layer A: deterministic sport state

`S_t` includes observed contest state, participants, environment, known availability, and latent-state posterior summaries. It excludes market prices from the core ground-truth path except in a separately identified ablation channel.

### 8.2 Layer B: ground-truth distribution

Estimate:

```text
P_sport(Y_{t:t+h} | S_t, history_available_at_t)
```

Outputs may include:

- categorical micro-event distribution;
- survival curve for time to boundary/event;
- conditional transition matrix;
- count distribution for runs/points;
- quantiles and full parametric/empirical CDF;
- epistemic and aleatoric uncertainty components;
- out-of-distribution score.

Topology:

1. sport-specific structural prior/model;
2. CatBoost residual specialists for nonlinear contextual effects;
3. ensemble/bootstrapped uncertainty;
4. route-specific point-in-time calibrator.

Examples:

- baseball: base/out run expectancy + competing PA hazards + boosted residual;
- basketball: possession duration survival + points mass function + lineup effects;
- football: drive terminal-event hazards + points distribution.

Do not force one universal label across sports.

For the pregame launch, compute the complete relevant joint distribution rather than training a disconnected binary model for every displayed market. Examples:

- MLB: joint team-run distributions by innings 1–5 and their F3/F5 aggregates;
- basketball: Q1 and Q2 team-point distributions and coherent first-half aggregate;
- football: Q1 and Q2 scoring-event/team-point distributions and coherent first-half aggregate.

This lets a newly posted line such as F5 4.0, 4.5, or 5.0 be priced immediately from the same distribution and enforces consistency between component periods and the half/F5 total.

### 8.3 Layer C: market/public pricing distribution

Estimate:

```text
P_market(Y | book_t, trades_{≤t}, venue, lifecycle, public_signals_{≤t})
```

This is not simply the midpoint:

- convert executable quotes to outcome probabilities;
- remove vig/overround coherently across mutually exclusive outcomes;
- estimate latent efficient price with spread/depth and microstructure features;
- model expected price at the earliest feasible execution time;
- quantify market uncertainty from spread, depth, volatility, and venue state.

Where a two-sided binary contract has complement-consistent prices, use both sides. Where books publish American/decimal odds without an exchange book, treat the quote as a snapshot with no inferred depth.

### 8.4 Layer D: calibration

Calibrate `P_sport` and `P_market` independently, then validate their joint divergence. Use calibration data disjoint from base-model fitting. Candidate methods:

- beta/logistic calibration for binary outcomes;
- isotonic only with adequate route sample size;
- Dirichlet/vector scaling for multiclass;
- conformalized quantile intervals where exchangeability assumptions are sufficiently local;
- hierarchical shrinkage toward league/global calibrators for sparse routes.

Calibration keys start with:

```text
sport × league × market_family × horizon_bucket × latency_tier × season_regime
```

Fall back through a declared hierarchy. The response states which level was used. Proper scoring rules, calibration, and sharpness are the correct framework for probabilistic forecasts ([Gneiting & Raftery](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf)).

### 8.5 Layer E: divergence specialist

The upgraded CatBoost engine predicts both sport outcomes and residual error:

```text
d_raw = P_sport_cal - P_market_cal
```

It also estimates:

- expected post-latency sport probability;
- expected executable price;
- distribution of slippage;
- fill probability;
- probability the window remains open;
- realized net return conditional on attempted action;
- probability of adverse selection.

No direct leakage is allowed from future book updates, closing lines, final corrections, or post-window text.

### 8.6 Layer F: opportunity and allocation

The upgraded AutoGluon engine consumes only frozen upstream outputs and point-in-time features. It estimates:

- `P_positive_net_return`;
- net return quantiles;
- expected CLV;
- fill probability;
- decision validity duration;
- risk-adjusted opportunity utility.

The final allocator is deterministic constrained optimization, not an opaque model:

```text
maximize Σ x_i * conservative_utility_i - concentration_penalty - drawdown_penalty
```

subject to bankroll, game, sport, market, participant, correlated-state, venue, and concurrent-window limits.

Train AutoGluon with latency/memory-aware candidates and distill/prune for serving. AutoGluon supports saving/loading predictors and deployment-oriented presets; loaded artifacts must be trusted because loading uses pickle ([AutoGluon essentials](https://auto.gluon.ai/stable/tutorials/tabular/tabular-essentials.html), [in-depth inference guidance](https://auto.gluon.ai/stable/tutorials/tabular/tabular-indepth.html)).

### 8.7 Text and multimodal path

The existing owned tokenizer and compact Torch encoder are usable offline/nearline after extension. Hot-path text should enter as:

- verified structured status codes;
- timestamped entity-linked features;
- fixed embeddings computed before decision cutoff.

No rented traditional LLM is required. A locally owned/trainable encoder can be trained on licensed text. Generative explanation is outside the decision path.

### 8.8 Computer vision

CV is future capability only. Activation prerequisites:

- lawful, stable video/tracking rights;
- synchronized source timecode;
- measured capture/decode/inference latency;
- labeled evaluation corpus;
- fallback behavior;
- evidence it improves forward metrics after latency.

Until then, tracking fields are consumed only from actual licensed structured feeds.

### 8.9 Reinforcement learning boundary

Trade One v1 uses supervised probabilistic forecasting plus constrained decision optimization. It does **not** claim RL.

RL experimentation may begin only if logs contain:

- state before every eligible action;
- complete action set including pass/cancel/reduce;
- actual chosen action and size;
- logging-policy probability/propensity;
- fills, partial fills, cancellations, costs, and delayed rewards;
- terminal and intermediate reward definition;
- support/overlap diagnostics;
- a valid off-policy evaluation plan.

Promotion would require importance-sampling diagnostics plus a doubly robust OPE estimator and conservative confidence bounds. Doubly robust OPE is explicitly designed to estimate a new policy from data collected under another policy ([Jiang & Li, ICML 2016](https://proceedings.mlr.press/v48/jiang16.html)). Without these elements the system remains a contextual forecasting and optimization system.

---

## 9. Probability and pricing math

### 9.1 Remove vig

For decimal odds `o_k`, raw implied probability is `q_k = 1/o_k`. A simple proportional no-vig normalization is:

```text
p_market,k = q_k / Σ_j q_j
```

For exchange contracts use executable bid/ask prices and fees instead of sportsbook overround. Proportional normalization is only a baseline; compare power and Shin-style transforms by calibration, not aesthetics.

### 9.2 Executable expected value

For a binary contract paying `1` per unit, buy price `a`, fee `f`, expected slippage `s`, and calibrated sport probability `p`:

```text
EV_unit = p*(1-a-f-s) + (1-p)*(-a-f-s)
        = p - a - f - s
```

If loss/payoff conventions differ, calculate from the venue settlement cash flows. Never mix American-odds profit formulas with contract-price formulas.

For a two-outcome sportsbook bet with decimal odds `o` and unit stake:

```text
EV = p*(o-1) - (1-p)
```

### 9.3 Latency adjustment

At decision time `t`, execution happens around `t+L`. Model:

```text
p_exec = E[P_sport(Y | S_{t+L}) | information at t]
a_exec = E[executable ask at t+L | book at t]
```

Then:

```text
d_net = p_exec - a_exec - fees - expected_slippage
```

Latency is a distribution by route, not a fixed global constant. Backtests sample from measured gateway, compute, network, and venue acknowledgment latency.

### 9.4 Uncertainty adjustment

Use a conservative lower bound:

```text
d_conservative = E[d_net] - λ_route * SD(d_net) - liquidity_penalty - OOD_penalty
```

or use a lower expected-value quantile. `READY` requires `d_conservative > threshold_route`.

### 9.5 Market depth and size

For requested quantity `Q`, traverse the ask ladder:

```text
VWAP(Q) = Σ price_l * filled_qty_l / Q
```

The opportunity is recomputed at `VWAP(Q)`, not top-of-book, and is capped by predicted fill probability and risk. Posted size is not guaranteed fill.

### 9.6 Kelly boundary

Sizing may use fractional Kelly only after uncertainty and correlation controls:

```text
f* = (b*p - (1-p)) / b
stake_fraction = min(cap, max(0, κ * f* * reliability_factor))
```

`κ` begins at 0 in shadow mode and remains small in production. Portfolio stress limits override Kelly. Model uncertainty, estimated correlations, and parameter error make unconstrained Kelly unacceptable.

### 9.7 Distribution coherence

- Event probabilities sum to one within tolerance.
- Quantiles are non-crossing.
- Binary complements reconcile after fees/venue conventions.
- Nested markets obey monotonicity where settlement rules imply it.
- State-transition probabilities respect impossible-event masks.

Violations produce `PASS` and a quality event.

---

## 10. Latency tiers and budgets

### 10.1 Honest service tiers

| Tier | Intended windows | Target decision p95* | Infrastructure |
|---|---|---:|---|
| T0 research | replay/offline | no live SLO | batch CPU/GPU training |
| T1 boundary | half-innings, quarters, drives | ≤1,500 ms after canonical boundary | managed containers acceptable |
| T2 live | PA, possessions, play sequences | ≤350 ms after canonical event | warm dedicated CPU containers, streaming |
| T3 ultra-live | pitch/sub-play | ≤100 ms | colocated/licensed low-latency feeds; not v1 |

`*` Decision latency excludes provider event-to-gateway delay but the UI and audit must show both separately. Actionability uses total information age.

### 10.2 T2 internal budget

| Stage | p95 budget |
|---|---:|
| gateway decode/auth | 20 ms |
| canonicalization/reducer | 25 ms |
| feature snapshot | 30 ms |
| ground-truth inference | 80 ms |
| market inference | 35 ms |
| calibration/divergence | 20 ms |
| grading/risk | 25 ms |
| serialization/publish | 20 ms |
| reserve | 95 ms |

These are acceptance targets, not achieved measurements.

Cloud Run executes containers with configurable CPU but can scale to zero and has disposable local filesystems; minimum warm instances or dedicated always-on workers are required for live tiers. Cloud SQL is not model-serving compute ([Cloud Run overview](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run), [container contract](https://docs.cloud.google.com/run/docs/container-contract)).

### 10.3 Staleness gates

Each response carries:

```text
sport_state_age_ms
book_age_ms
text_age_ms
model_compute_ms
decision_age_ms
```

The tightest applicable route threshold wins. A market update cannot “refresh” stale sport state.

---

## 11. Risk controls

### 11.1 Pre-decision hard gates

- feed health and sequence continuity;
- state invariant validity;
- event/market identity match;
- market open and not suspended;
- minimum executable depth;
- maximum spread and volatility;
- sport and book freshness;
- calibration coverage and sample floor;
- OOD/drift limit;
- settlement-rule match;
- minimum conservative EV;
- drawdown/exposure/correlation limits;
- duplicate/conflicting decision prevention.

### 11.2 Exposure hierarchy

Caps exist at:

- account/bankroll;
- venue;
- sport/league;
- game;
- team/participant;
- window;
- market family;
- outcome cluster;
- correlated latent factor (same pitcher, lineup, pace, weather, score path);
- concurrent open decisions.

Correlation groups are versioned and conservative. Unknown correlation increases penalty rather than being treated as zero.

### 11.3 Kill switches

Automatic halt on:

- sequence gap beyond recovery limit;
- settlement or identity mismatch;
- clock/score/base-out/down-state impossibility;
- price checksum failure or crossed locked book;
- latency SLO breach over rolling window;
- abnormal rejection/fill/slippage;
- daily loss or drawdown limit;
- calibration breach after sufficient outcomes;
- model artifact or feature-schema mismatch.

Manual kill switches exist globally, per venue, sport, game, provider, model, and market family. Halts are durable Cloud SQL rows plus immediate in-memory broadcasts.

### 11.4 Abstention contract

Every non-action returns structured codes:

```text
STALE_SPORT_STATE
STALE_BOOK
BOOK_GAPPED
INSUFFICIENT_DEPTH
SPREAD_TOO_WIDE
NO_CALIBRATOR_COVERAGE
OUT_OF_DISTRIBUTION
NEGATIVE_COST_ADJUSTED_EDGE
UNCERTAINTY_TOO_HIGH
CORRELATION_CAP
DRAWDOWN_HALT
WINDOW_EXPIRED
SETTLEMENT_RULE_MISMATCH
```

Abstention rate is monitored. A model cannot improve reported performance merely by passing on nearly everything; coverage-performance curves are promotion artifacts.

---

## 12. APIs

All mutation endpoints require idempotency keys, authenticated service identity, schema version, and trace ID. Timestamps are UTC RFC 3339 with declared precision.

### 12.1 Ingestion

```http
POST /v1/ingest/sport-events
POST /v1/ingest/book-events
POST /v1/ingest/text-signals
POST /v1/ingest/weather-signals
```

Return `202 Accepted` with raw object generation, admission status, and canonicalization cursor. Invalid records go to quarantine without disappearing.

### 12.2 Live state

```http
GET /v1/games/{game_id}/state
GET /v1/games/{game_id}/timeline?after_sequence=...
GET /v1/games/{game_id}/windows
WS  /v1/stream/games/{game_id}
```

### 12.3 Market

```http
GET /v1/markets/{market_id}/book?depth=10
GET /v1/games/{game_id}/markets
GET /v1/market-release-watch?date=...&status=DISCOVERED
WS  /v1/stream/markets/{market_id}
WS  /v1/stream/market-releases?date=...
```

### 12.4 Intelligence

```http
POST /v1/intelligence/evaluate
GET  /v1/decisions/{decision_id}
GET  /v1/games/{game_id}/opportunities
WS   /v1/stream/opportunities?game_id=...
```

Pregame preparation endpoints:

```http
POST /v1/slates/{date}/prepare
GET  /v1/slates/{date}/readiness
POST /v1/games/{game_id}/refresh-forecast
GET  /v1/games/{game_id}/micro-period-distributions
```

Evaluation request references immutable snapshot IDs:

```json
{
  "game_state_snapshot_id": "...",
  "book_snapshot_ids": ["..."],
  "window_id": "...",
  "requested_at": "...",
  "mode": "live|shadow|replay"
}
```

Response:

```json
{
  "decision_id": "...",
  "state_hash": "...",
  "as_of": "...",
  "expires_at": "...",
  "p_sport": {"mean": 0.612, "q05": 0.55, "q95": 0.67},
  "p_market": {"mean": 0.548, "q05": 0.53, "q95": 0.57},
  "costs": {"fees": 0.006, "slippage": 0.009},
  "opportunity": {
    "raw_divergence": 0.064,
    "net_ev": 0.049,
    "conservative_ev": 0.018,
    "status": "READY"
  },
  "liquidity": {"fill_probability": 0.78, "max_executable_quantity": 90},
  "risk": {"allowed": true, "recommended_exposure": 12, "codes": []},
  "lineage": {
    "control_version": "...",
    "sport_model_version": "...",
    "market_model_version": "...",
    "calibrator_version": "...",
    "allocator_version": "...",
    "feature_snapshot_id": "..."
  },
  "latency": {"sport_state_age_ms": 112, "book_age_ms": 38, "compute_ms": 97}
}
```

### 12.5 Manual handoff and paper tracking

```http
POST /v1/paper-positions
PATCH /v1/paper-positions/{id}
POST /v1/opportunities/{id}/copy-event
```

These endpoints record hypothetical tracking and product analytics only. They do not contact a sportsbook. A user may optionally record the odds they personally obtained so calibration and decision quality can be compared with the observed reference price. Trade One stores no sportsbook password, API key, session token, or wagering credential.

### 12.6 Governance/replay

```http
POST /v1/replays
GET  /v1/replays/{id}
POST /v1/models/{version}/evaluate
POST /v1/models/{version}/promote
POST /v1/halts
DELETE /v1/halts/{halt_id}
```

Promotion requires a signed evaluation bundle and two-person approval for production.

---

## 13. Storage and compute

### 13.1 Cloud SQL: persistence, not inference

Cloud SQL PostgreSQL stores:

- canonical identities and mappings;
- event/market metadata and settlement rules;
- reducer snapshots and current pointers;
- feature/decision metadata and lineage;
- model/calibrator registry;
- configurations and promotion decisions;
- exposures, simulated/real orders, fills, settlements;
- risk halts and audit records;
- replay manifests and cursors.

Cloud SQL is a fully managed relational database service. It does not provide the CPU/GPU process that runs CatBoost, AutoGluon, Torch, state actors, or streaming reducers ([Google Cloud SQL FAQ](https://docs.cloud.google.com/sql/docs/postgres/faq)).

### 13.2 Object storage

Object storage holds:

- raw provider payloads;
- canonical ledger partitions;
- book snapshots/checkpoints;
- replay bundles;
- point-in-time training datasets;
- model/calibrator artifacts;
- evaluation reports;
- feature dictionaries.

Every registry row records artifact URI, object generation, checksum, code commit, environment lock, and signature.

### 13.3 Hot state

Use in-process memory or a controlled low-latency cache for:

- current game state;
- rolling feature windows;
- active order books;
- current exposure counters;
- model artifacts.

Hot state is recoverable and not authoritative.

### 13.4 Compute services

| Workload | Compute |
|---|---|
| adapters/gateways | warm CPU containers |
| reducers/state actors | always-on CPU workers |
| CatBoost inference | CPU native `.cbm` by default |
| AutoGluon inference | pruned/distilled CPU predictor |
| compact Torch encoder | ONNX INT8 CPU when quality holds |
| model training | owned CPU/GPU jobs as required |
| backtest/replay | batch CPU, optional GPU for training only |

CatBoost’s native format is generally faster than ONNX on common x86-64 and preserves categorical support; ONNX-ML export supports only numerical features. Therefore native `.cbm` is the baseline for the divergence engine, with ONNX only after parity/latency testing ([CatBoost ONNX documentation](https://catboost.ai/docs/en/concepts/apply-onnx-ml)).

### 13.5 Minimum Cloud SQL logical schema

Schemas/tables:

```text
core.providers, core.entities, core.entity_aliases, core.games
ledger.sport_events, ledger.market_events, ledger.text_signals, ledger.weather_signals
state.game_snapshots, state.market_snapshots, state.active_windows
features.feature_sets, features.feature_snapshots, features.lineage_edges
models.registry, models.calibrators, models.evaluations, models.promotions
decisions.forecasts, decisions.opportunities, decisions.abstentions
risk.policies, risk.exposures, risk.halts
execution.orders, execution.fills, execution.settlements
replay.manifests, replay.runs, replay.diffs
audit.api_requests, audit.config_changes, audit.security_events
```

High-volume raw deltas should be compacted to object storage partitions; Cloud SQL keeps indexed metadata, selected canonical rows, checkpoints, and audit references. It is not the tick archive.

---

## 14. Point-in-time features

Every feature definition includes:

```text
name, dtype, owner, source fields, transform version,
availability_time expression, freshness limit,
window semantics, null policy, leakage tests, route coverage
```

Feature rows are built by an as-of join:

```text
feature.available_at <= decision_cutoff
```

not by event date alone.

### Required feature families

- sport state and transition history;
- participant/team priors computed only from earlier games;
- live latent-state posterior;
- injuries/availability known by cutoff;
- weather forecast revision known by cutoff;
- market book/depth/trade features;
- venue lifecycle/fees;
- text signals first observed by cutoff;
- latency and data-quality features;
- model disagreement and calibration route;
- active exposures/correlation state.

### Leakage test suite

- inject future records and prove exclusion;
- move `received_at` later than cutoff and prove exclusion;
- replay a corrected event with its original publication time;
- verify closing prices never enter live feature rows;
- verify season aggregates are lagged;
- verify labels/settlements are inaccessible to online feature code;
- train/serve feature parity hash;
- verify identity mappings use the as-of version.

---

## 15. Backtesting and replay

### 15.1 Three evaluation modes

1. **Forecast replay:** score `P_sport` at every eligible boundary.
2. **Market replay:** reconstruct observed books and `P_market`.
3. **Policy replay:** simulate decisions, latency, queue/fill, costs, correlation, and risk.

Do not infer trading performance from forecast accuracy alone.

### 15.2 Execution simulator

Minimum models:

- market order consuming visible depth;
- limit order queue position with pessimistic and neutral variants;
- partial fills;
- cancel/replace latency;
- book gaps and suspensions;
- venue rejects;
- price-time evolution during sampled latency;
- fee and settlement rules;
- no fill when market closes before acknowledgment.

Report results under:

- quoted-fill fantasy baseline (diagnostic only);
- conservative marketable execution;
- queue-aware limit execution;
- latency stress at p50/p95/p99;
- 2× spread/slippage and reduced depth;
- feed correction and outage scenarios.

### 15.3 Walk-forward design

- split by event time, grouped by game and season regime;
- purge/embargo overlapping horizons;
- calibrator fits only on data after base-model training and before test;
- tune only within past blocks;
- final test blocks remain untouched;
- report route and coverage;
- bootstrap confidence intervals clustered by game/day.

### 15.4 Baselines

Every candidate must beat relevant baselines:

- no-vig market probability;
- current price/midpoint;
- sport structural model without ML;
- existing champion;
- no-text/no-weather/no-market-feature ablations;
- random/pass-only policy where applicable;
- zero-latency and realistic-latency gap.

### 15.5 Replay determinism

Same manifest and seed must reproduce:

- canonical event sequence and state hashes;
- feature snapshot hashes;
- model outputs within declared numeric tolerance;
- decisions and abstention codes;
- simulated fills under a fixed random stream.

---

## 16. Evaluation and promotion gates

### 16.1 Forecast metrics

| Output | Metrics |
|---|---|
| binary/multiclass events | log loss, Brier, classwise reliability, adaptive ECE |
| continuous count/margin | CRPS, pinball loss by quantile, interval coverage/width |
| survival/time-to-event | time-dependent Brier, integrated Brier, calibration |
| transition distribution | log likelihood, impossible-transition rate |

Always report skill versus market and structural baselines, with uncertainty intervals.

### 16.2 Market/opportunity metrics

- closing-line value using a declared close;
- realized net return after fees/slippage;
- fill rate and fill calibration;
- expected-vs-realized slippage;
- opportunity precision by conservative-EV bucket;
- maximum drawdown, downside deviation, turnover;
- exposure concentration and correlated loss;
- decision coverage/abstention;
- latency and staleness distributions.

### 16.3 Data/platform gates

- zero known critical point-in-time leakage;
- ≥99.99% deterministic replay state-hash agreement on certified corpus;
- 100% decision lineage completeness;
- ≥99.9% API availability for T1/T2 service during shadow test;
- route-specific p95 latency SLO met and p99 monitored;
- no unresolved sequence gap produces `READY`;
- correction invalidation tested;
- disaster recovery replay tested.

### 16.4 Model promotion gate

A challenger promotes only if all are true:

1. statistically credible improvement in primary proper score or non-inferiority plus material net utility;
2. no material calibration regression overall or in protected high-volume routes;
3. positive conservative net return and CLV in untouched forward shadow;
4. drawdown and concentration within policy;
5. latency/memory within serving budget;
6. abstention coverage above minimum and below pathological maximum;
7. no integrity, lineage, settlement, or schema failures;
8. stress tests pass;
9. shadow duration and sample floors are met;
10. signed artifact and rollback are verified.

Initial sample floors:

- ≥5,000 forecast opportunities and ≥500 settled decisions overall;
- ≥500 opportunities per promoted route;
- ≥30 active event-days spanning multiple opponents/venues;
- confidence interval on net return excludes the unacceptable-loss threshold.

These are admission floors, not proof of generality.

### 16.5 Rollout

```text
offline challenger → historical replay → live shadow → 1% canary →
10% canary → controlled champion
```

Automatic rollback on integrity, calibration, latency, or risk breach. Champion/challenger aliases and immutable artifact versions are explicit; model registry aliases are a recognized pattern, but the owner may implement them in Cloud SQL rather than depend on a hosted registry ([MLflow registry aliases](https://mlflow.org/docs/latest/ml/model-registry/tutorial/)).

---

## 17. Existing engine reuse audit

The reviewed package is 2,855 lines across the principal documents, schema, and Python modules. It implements a coherent pregame three-engine prototype. It does **not** yet implement a live event ledger, book reconstruction, sport-specific reducers, latency-aware execution, or true live-state contracts.

### 17.1 Reuse unchanged

“Unchanged” means copied into the new repository with provenance and tests, not imported from or modified in the original package.

| Existing module | Decision | Why |
|---|---|---|
| `losses.py::pinball` | reuse unchanged initially | generic quantile loss |
| `walk_forward.py::recency_weights` | reuse unchanged | generic time-decay helper |
| `calibration.py::CalibrationState` serialization shape | reuse unchanged initially | generic state container; algorithms extend |
| `formula_runtime.py` fingerprint/lineage concept | reuse unchanged initially | controlled proprietary formula boundary is sound |
| HMAC verification pattern in `control_plane.py` | reuse pattern, not file | deterministic signature check remains valid |

Very little should be copied literally unchanged because current contracts are pregame prop-oriented.

### 17.2 Extend materially

| Existing module | Required extension |
|---|---|
| `contracts.py` | replace pregame `as_of <= event_start` rule with live availability clocks, revisions, sequences, correction lineage, and event-type schemas |
| `control_plane.py` | durable dedup/collision state, raw object generations, provider sequence checks, schema registry, quarantine workflow |
| `ontology.py` | game/period/possession/drive/PA/pitch, venue market identities, versioned as-of mappings |
| `api_client.py` | streaming/WebSocket adapters, resumable sequence checkpoints, backpressure, feed authentication |
| `tensorizer.py` | sport-state masks, variable transition histories, feature availability metadata, train/serve parity |
| `tokenizer.py` | live entity vocabulary, timestamped signal codes, safe unknown behavior |
| `model.py` | live state/transition objectives, sport adapters, distribution/survival heads; keep owned compact encoder concept |
| `training.py` | grouped purged event-time splits, calibrator separation, replay manifests, route metrics |
| `inference.py` | immutable snapshot references, deadlines, state/model hashes, CPU benchmark |
| `export.py` | per-component parity and quantization acceptance; native CatBoost remains separate |
| `drift.py` | route/latency/calibration/outcome drift, minimum sample logic, alert persistence |
| `governance.py` | coverage, CRPS/survival, drawdown, integrity, shadow/canary, signed approvals |
| `repository.py` / `cloudsql/schema.sql` | full normalized schemas, revisions, decisions, risk, execution, replay; move raw bulk payloads to object storage |
| `service.py` / `cli.py` | split ingestion, state, intelligence, governance, replay, and execution surfaces |
| `catboost_formula_engine.py` | distributions, sport/market separation, latency/fill/slippage targets, route specialists, artifact compatibility |
| `autogluon_pick_engine.py` | live opportunity rows, return quantiles, fill/validity targets, portfolio correlation and concurrent exposure |
| `challenger.py` | proper-score suite, clustered intervals, coverage, risk/latency metrics |
| `engine_chain.py` | replace synchronous list chain with snapshot-driven DAG and explicit dual probability layer |
| `engine_contracts.py` | replace `PropOpportunity`, `CatBoostPropPrediction`, and `OptimalPick` with live forecast/opportunity/allocation contracts |

### 17.3 Replace

| Existing behavior | Reason |
|---|---|
| `IntelligenceEnvelope.validate()` forbids `as_of > event_start` | fundamentally incompatible with in-game operation |
| in-memory `ControlPlane.seen` | lost on restart and cannot coordinate replicas |
| raw archive filename by record ID | overwrites revisions and is not an immutable event ledger |
| generic numeric `temporal_history` list | lacks typed event time, availability, masks, and lineage |
| `PropOpportunity` static line/over/under contract | cannot express books, depth, fills, lifecycle, windows, or state revisions |
| grade-centric `OptimalPick` contract | hides distributions, executable price, expiry, and risk |
| one-call synchronous `POST /v1/optimal-picks` as live architecture | unsuitable for ordered streaming state and deadline-aware inference |

### 17.4 Net-new components

1. Provider adapter SDK and schema registry.
2. Immutable raw log writer.
3. Canonical event reconciler.
4. Sport rule/reducer adapters.
5. Window lifecycle engine.
6. Per-game live state actor.
7. Market catalog and settlement-rule registry.
8. Order-book builder with gap recovery.
9. Rolling microstructure feature service.
10. Ground-truth sports-state model service.
11. Market/public-pricing model service.
12. Hierarchical calibration service.
13. Latency and executable-price model.
14. Fill/slippage/adverse-selection model.
15. Deterministic risk/exposure service.
16. Replay and execution simulator.
17. Opportunity stream gateway.
18. Governance/promotion controller.
19. UI live board, game room, ticket, replay lab, governance console.
20. Manual copy/pin/paper-tracking workflow and opportunity-expiry alerts.
21. Pregame slate preparer and Market Release Watch.

### 17.5 Existing claims that require revalidation

The source README describes “immutable archive,” “point-in-time,” “Cloud SQL tables,” “CPU inference,” and “rung-7 capability architecture.” For Trade One:

- local JSON writes are not sufficient immutable archival;
- pregame timestamp validation is not live point-in-time integrity;
- the existing Cloud SQL schema is a useful seed, not a live ledger;
- CPU servability must be benchmarked per final artifact;
- capability is not production readiness until licensed feeds, real corpus, latency, and forward evaluation exist.

The original package remains untouched.

---

## 18. Build plan

### Stage 0 — architecture lock and evidence pack (2–3 weeks)

Deliver:

- approved schemas and API contracts;
- MLB state reducer specification;
- venue/feed capability matrix and data rights review;
- latency measurement harness;
- threat model and settlement-rule inventory;
- final reuse migration map;
- acceptance-test catalog.

Exit:

- no open ambiguity in event clocks, revision semantics, market outcome definitions, or first-sport scope;
- sample real payloads replay through schema validators;
- providers and venues contractually permit intended use.

### Stage 1 — pregame MLB slate and market-release foundation (4–6 weeks)

Build schedule/team/player identity, point-in-time probable starters and lineups, weather revisions, pregame feature snapshots, F3/F5 and inning 1–5 market definitions, Market Release Watch, Morning Slate, and opening-line history.

Exit:

- forecasts are ready before the derivative market for the certified test slate;
- newly posted markets are discovered and canonically mapped within the provider/cadence SLO;
- every alert preserves the first seen quote and its exact receipt time;
- pitcher, lineup, weather, or market changes invalidate/recompute affected opportunities;
- no play-by-play dependency exists for launch operation.

### Stage 2 — deterministic MLB live ledger and replay (optional next layer, 4–6 weeks)

Build adapters, raw object log, canonicalizer, identity, reducer, state snapshots, half-inning/PA windows, replay UI skeleton, and Cloud SQL core.

Exit:

- certified historical games reproduce final score and every base/out/count transition;
- ≥99.99% state-hash replay repeatability;
- all corrections retained and testable;
- no learned model required.

### Stage 3 — market depth and advanced simulation (4–6 weeks)

Build market catalog, settlement rules, snapshot/delta books, gap recovery, microstructure features, execution simulator, and simulated ticket.

Exit:

- sequence-gap tests pass;
- book snapshots reproduce provider checksums where available;
- simulator handles partial fills, suspension, expiry, fees, and latency;
- live execution remains disabled.

### Stage 4 — dual probability MVP (6–8 weeks)

Build MLB structural model, CatBoost residual specialists, separate market model, calibrators, distribution API, drift monitors, and CPU serving benchmarks.

Exit:

- untouched forward forecast metrics beat declared structural baseline;
- probability coherence and calibration gates pass;
- CPU p95 meets T1, then T2 target where feed latency permits;
- every output has full lineage.

### Stage 5 — opportunity/portfolio shadow (6–8 weeks)

Upgrade AutoGluon targets, build conservative EV/fill/slippage models, risk engine, live board/game room, and shadow decisions.

Exit:

- ≥30 active event-days;
- positive conservative CLV and acceptable net-return interval;
- drawdown/exposure/coverage gates pass;
- shadow decisions remain read-only and cannot invoke any sportsbook action.

### Stage 6 — controlled read-only production (timing evidence-driven)

Deploy live read-only intelligence with canary limits, opportunity alerts, manual copy/pin workflows, paper tracking, monitoring, and automatic model rollback. There is no wager-routing stage.

### Stage 7 — basketball and football adapters

Each sport repeats deterministic reducer certification and route-specific modeling. Shared infrastructure is reused; sport state is not forced into baseball schemas.

---

## 19. Architecture acceptance criteria

Implementation must not begin beyond Stage 0 until these are accepted:

### Data

- [ ] Canonical sport, book, text, weather, state, window, forecast, decision, order, fill, and settlement schemas versioned.
- [ ] All four clocks and source precision retained.
- [ ] Raw object generation and checksum recorded before downstream acknowledgment.
- [ ] Idempotency, collision, correction, gap, and quarantine semantics tested.
- [ ] As-of identity and feature joins specified.

### Models

- [ ] `P_sport` and `P_market` cannot share target-derived or future features.
- [ ] Each output distribution has a proper scoring rule.
- [ ] Calibration data is disjoint and hierarchy declared.
- [ ] Continuous outputs include quantiles/CDF representation.
- [ ] CPU artifact, memory, cold/warm latency, and parity thresholds defined.
- [ ] No RL label appears in code/product copy without OPE prerequisites.

### Opportunity/risk

- [ ] Fee, vig, slippage, fill, latency, and depth math is venue-specific.
- [ ] Decisions expire at a sport/market boundary.
- [ ] Risk service is authoritative and separately deployed.
- [ ] Stale/gapped/incoherent inputs can only produce `PASS/HALTED`.
- [ ] Product and API contain no sportsbook execution or credential capability.

### Platform

- [ ] Cloud SQL and compute responsibilities are separated.
- [ ] Raw high-volume archive is object storage, not database-only.
- [ ] Live state can rebuild from ledger after process loss.
- [ ] Replay manifest reproduces state/features/decisions.
- [ ] Observability covers provider-to-gateway and internal latency separately.

### Governance

- [ ] Champion/challenger, shadow/canary, rollback, and artifact signatures implemented.
- [ ] Promotion includes calibration, CRPS/log loss/Brier, CLV, return, latency, coverage, and drawdown.
- [ ] Protected route regressions and sample floors are enforced.
- [ ] Audit lineage is complete for 100% of emitted `READY` decisions.

---

## 20. Security and ownership

- All data-provider secrets remain in a managed secret service; never in Cloud SQL payloads or model artifacts.
- Separate service accounts for ingestion, modeling, risk guidance, and application delivery.
- Sportsbook credentials are never requested, accepted, stored, or transmitted.
- Signed configuration/model manifests and checksum verification at load.
- Trusted artifacts only; this is especially important for AutoGluon predictor loading.
- Least-privilege database roles and append-only audit permissions.
- Data license/retention rules are represented by provider and enforced in archive lifecycle.
- No external rented LLM is required to operate the product.
- Owned source, feature definitions, training data manifests, model artifacts, calibrators, and evaluation reports form the product IP boundary.

---

## 21. Primary-source research notes

The architecture relies on these current facts:

- Kalshi’s official API documentation describes real-time market data/trade execution and order-book WebSocket channels; integration remains venue- and jurisdiction-specific ([Kalshi API](https://docs.kalshi.com/welcome), [order books](https://docs.kalshi.com/api-reference/market/get-multiple-market-orderbooks)).
- Polymarket documents near-real-time WebSocket streams for order books and trades; it is an example of an exchange feed, not an assumed production venue ([Polymarket WebSocket overview](https://docs.polymarket.com/market-data/websocket/overview)).
- MLB describes Statcast as tracking technology and Baseball Savant as a real-time gamefeed surface. Public availability does not by itself establish a licensed low-latency production feed ([MLB Statcast glossary](https://www.mlb.com/glossary/statcast)).
- NFL describes Next Gen Stats as player and ball tracking for every play. Access and latency must still be contracted, not inferred from public descriptions ([NFL Football Operations](https://operations.nfl.com/gameday/technology/nfl-next-gen-stats)).
- Google’s current Pub/Sub ordering documentation states within-key ordering and at-least-once delivery, with explicit latency/availability tradeoffs; hence application-level idempotency and reconciliation remain required ([Google Pub/Sub](https://docs.cloud.google.com/pubsub/docs/ordering)).
- Cloud SQL is managed PostgreSQL persistence, while Cloud Run/container workers supply compute. They are not interchangeable ([Cloud SQL PostgreSQL](https://cloud.google.com/sql/postgresql), [Cloud Run](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run)).
- CatBoost native inference is generally preferable on common x86-64 when categorical features matter; ONNX export has feature limitations ([CatBoost ONNX](https://catboost.ai/docs/en/concepts/apply-onnx-ml)).
- AutoGluon supports deployable saved predictors and CPU use, but serving candidates must be intentionally optimized and artifacts trusted ([AutoGluon FAQ](https://auto.gluon.ai/stable/tutorials/tabular/tabular-faq.html), [essentials](https://auto.gluon.ai/stable/tutorials/tabular/tabular-essentials.html)).

---

## 22. Tradovate-derived micro-window strategy framework

### 22.1 What transfers—and what does not

Tradovate is an active futures execution platform. Its current official materials emphasize a depth-of-market ladder, rapid order placement, server/exchange-held orders, OCO and OSO brackets, trailing stops, good-til-date instructions, simulation, full-depth market replay, order-flow displays, performance reporting, and account-level loss/drawdown controls ([Tradovate platform](https://www.tradovate.com/platform/), [API reference](https://partner.tradovate.com/resources/reference/api-cheat-sheet), [reports](https://partner.tradovate.com/resources/admin-dashboards/reports)).

Trade One should borrow this operating discipline:

- decide from executable depth, not the last displayed price;
- enter only when a defined setup and liquidity state coexist;
- attach exit, expiry, and maximum-loss intent at entry;
- cancel sibling exits when one completes;
- rehearse on event-by-event replay;
- impose session loss, drawdown, size, and product/window limits;
- preserve every submit, modify, cancel, reject, and fill timestamp;
- separate simulation from actual execution.

It should not blindly transfer:

- futures candlesticks, chart patterns, or indicator names;
- an assumption that every sports position is continuously fungible;
- stop-market behavior where the sports venue has no equivalent;
- the belief that visible depth guarantees a fill;
- the idea that “momentum” is predictive without sport-state conditioning;
- unlimited intragame turnover where fees, vig, suspensions, and thin books dominate.

Sportsbook wagers commonly cannot be exited through an open order book. A “cash out” quote is a new venue price, not a guaranteed stop. Trade One therefore treats “enter” and “exit” as **intelligence states**: when a setup first becomes favorable, when it weakens, and when it expires. The app never attempts either transaction. It labels market behavior so the user understands whether an independent exit may even be possible:

```text
TWO_SIDED_EXITABLE | OFFSETTABLE | CASHOUT_ONLY | HOLD_TO_SETTLEMENT
```

Quick-turn performance analytics are reported separately for each class. The app does not assume the user received a cash-out or offset price.

### 22.2 The Sport DOM

Trade One’s equivalent of a depth-of-market ladder is the **Sport DOM**, a sport-native decision surface rather than a copied futures UI.

For each micro-period outcome it shows:

- best executable entry and exit prices;
- cumulative depth at each price;
- spread and executable VWAP by proposed size;
- recent adds, cancels, trades, and price impact;
- `P_sport` fair-value band;
- `P_market` latent-price band;
- current sport state and next boundary;
- time/state remaining before expiry;
- suggested observation threshold, target state, invalidation state, and maximum age;
- optional user-entered paper exposure and correlated game context.

The center of the screen remains the inning, quarter, possession, or drive—not a price chart.

### 22.3 Canonical micro-period inventory

#### Baseball launch inventory

“First through fifth” is represented as several distinct, non-overlapping products:

| Window ID | Opens | Forced close/settlement boundary | Use |
|---|---|---|---|
| `MLB_INNING_1` … `MLB_INNING_5` | start of named inning | third out in bottom half, subject to settlement rules | individual inning side/total |
| `MLB_TOP_1` … `MLB_BOTTOM_5` | start of half-inning | third out | very short run/no-run windows |
| `MLB_F3` | first pitch | official completion of inning 3 | early game side/total |
| `MLB_F5` | first pitch | official completion of inning 5 | first-five side/total |
| `MLB_PA` | batter active | plate appearance settles | future ultra-short route |

The first production set is `MLB_F5` plus innings 1–5. Half-innings follow after book availability and latency prove sufficient. Plate appearances remain research until the complete feed-to-fill path is measured.

Required baseball context:

- probable/active pitcher confirmation;
- batting-order position and handedness;
- base/out/count state;
- pitcher pitch count, velocity/movement change, command proxy, times through order;
- bullpen availability for windows extending beyond the starter;
- park, roof, and point-in-time weather forecast;
- score-dependent strategy and leverage;
- venue suspension/settlement behavior.

#### Basketball launch inventory

| Window ID | Opens | Boundary | Use |
|---|---|---|---|
| `BASKETBALL_Q1` | opening tip | end Q1 | first-quarter side/total |
| `BASKETBALL_Q2` | start Q2 | end Q2 | second-quarter side/total |
| `BASKETBALL_H1` | opening tip | halftime | first-half side/total |
| `BASKETBALL_Q_WINDOW_N` | possession boundary | configured 2–5 minute clock boundary | future micro-window |

The launch set is Q1, Q2, and first half. Possession markets remain model/replay outputs until a tradable venue supports them with adequate liquidity.

Required context:

- confirmed starters and active lineup;
- substitutions and lineup continuity;
- possessions and pace posterior;
- foul/bonus state;
- timeouts and rest;
- shooting-location/quality distribution where licensed;
- score, clock, and end-of-quarter tactics.

#### Football launch inventory

| Window ID | Opens | Boundary | Use |
|---|---|---|---|
| `FOOTBALL_Q1` | kickoff | end Q1 | first-quarter side/total |
| `FOOTBALL_Q2` | start Q2 | halftime | second-quarter side/total |
| `FOOTBALL_H1` | kickoff | halftime | first-half side/total |
| `FOOTBALL_DRIVE` | possession begins | drive terminal event | future drive market |

The launch set is Q1, Q2, and first half. Drive-level execution follows only where settlement and liquidity exist.

Required context:

- possession, field position, down/distance, clock, timeouts;
- drive efficiency and play-rate posterior;
- personnel/injury updates;
- weather and field conditions;
- score-dependent play calling;
- expected possessions remaining.

### 22.4 Strategy templates

A strategy template is a versioned deterministic policy around probabilistic forecasts. The model supplies distributions; the template specifies when the system may act.

#### A. State-confirmed divergence

Purpose: enter when sport-state fair value moves materially before or further than the executable market.

```text
entry:
  P_sport_exec - executable_price - all_costs > threshold
  AND book_contiguous
  AND depth >= minimum
  AND sport_state_age <= limit
  AND divergence persists for confirmation interval

exit:
  target reached
  OR divergence closes
  OR state invalidates thesis
  OR time/state boundary reached
```

Example: a starting pitcher shows a verified velocity/command deterioration and reaches a high-stress pitch count, increasing the first-five run distribution. This is not an action until the adjusted distribution, price, depth, and remaining window all pass.

#### B. Order-flow-confirmed state move

Purpose: use market flow as confirmation that a new sports event is being incorporated, without treating the crowd as truth.

Conditions:

- canonical play materially changes state;
- trade intensity and order-flow imbalance move in the same direction;
- spread does not blow through limit;
- expected price impact has not already consumed the edge;
- `P_sport` remains beyond the executable price after sampled latency.

This is the closest analogue to DOM/tape confirmation.

#### C. Liquidity-shock mean reversion

Purpose: respond when a thin-book sweep or cancellation shock pushes price outside both the sport model and the estimated efficient market band.

Conditions:

- no simultaneous sport-state change explains the move;
- book is contiguous and has begun replenishing;
- price impact exceeds historically calibrated route threshold;
- reversion remains profitable after adverse-selection penalty;
- size is capped below replenished depth.

This template is disabled around injuries, reviews, scoring corrections, pitcher changes, and unknown feed gaps because “temporary” price shocks can reflect information Trade One has not received.

#### D. Boundary compression

Purpose: exploit improving certainty as an inning/quarter/half approaches completion.

The system recomputes remaining-event distributions after every transition. Entry is allowed only if:

- window is still open and tradable;
- remaining state sharply reduces outcome entropy;
- venue price lags after latency;
- exit/settlement timing is unambiguous.

This can be especially relevant to inning run/no-run, quarter totals, and first-half outcomes. It is not simply “bet the under late”; score, possession/base-out state, fouls, timeouts, and market price determine the distribution.

#### E. Relative-outcome consistency

Purpose: detect incoherence among logically related markets.

Examples:

- first-five team total vs first-five game total;
- Q1 side vs Q1 moneyline and spread distributions;
- first-half total vs component quarter totals.

Only combine markets when settlement definitions align. Opportunity is based on a joint distribution and executable multi-leg costs. This may be a relative-value or hedge setup, not risk-free arbitrage.

### 22.5 Opportunity playbooks

Tradovate’s OCO/OSO and GTD discipline translates into a read-only **Opportunity Playbook**:

```json
{
  "entry_signal": {
    "market_id": "...",
    "side": "yes",
    "maximum_reference_price": 0.51,
    "expires_on": "NEXT_CANONICAL_PLAY_OR_3_SECONDS",
    "status": "READY"
  },
  "follow_up_signals": {
    "target_reached": {"reference_price": 0.58},
    "thesis_invalidated": {
      "policy": "MAX_LOSS_OR_STATE_INVALIDATION",
      "max_price_loss": 0.05
    },
    "window_expired": {"boundary": "END_OF_INNING_3"}
  }
}
```

This is an information lifecycle, not a linked order. If the user manually marks a paper or real-world action, Trade One can track subsequent reference prices and state changes, but it still sends nothing to the sportsbook and makes no claim that an exit was available.

Additional policies:

- **State stop:** exit when the underlying sports thesis becomes false.
- **Price stop:** exit at a maximum executable loss, subject to liquidity.
- **Time stop:** exit before the modeled edge decays or the market suspends.
- **Profit target:** reduce/exit when market converges to conservative fair value.
- **Trailing fair-value lock:** ratchet an exit threshold only when `P_sport`, not price alone, moves favorably.
- **Forced boundary:** cancel unfilled entries and resolve/exit working exposure before the configured boundary when possible.

### 22.6 Fast-turn decision loop

```text
OBSERVE state/book
  → ESTIMATE P_sport and P_market at expected fill time
  → QUALIFY setup
  → GRADE opportunity from liquidity and risk
  → PUBLISH ready signal with expiry
  → UPDATE target/invalidation status
  → EXPIRE signal at boundary
  → SCORE observed prices, state, and paper outcome
```

No new entry is accepted while an earlier decision uses a stale state revision. Model recomputation after each play does not mean a trade after each play; the abstention gate should reject most states.

### 22.7 Micro-window risk profile

Initial configuration:

| Control | Shadow default |
|---|---:|
| App-routed risk | Always 0; Trade One cannot wager |
| Concurrent highlighted opportunities per game | 1 |
| Correlated baseball F5 + inning exposure | treated as one cluster |
| New entries after boundary warning | disabled |
| Maximum spread | route-specific 90th percentile cap or tighter |
| Minimum depth | ≥5× proposed size across executable levels |
| Daily stop | fixed loss plus rolling drawdown rule |
| Consecutive model/risk failures | automatic route halt |
| Stale state/book | unconditional pass |

Alert frequency and optional paper-tracking guidance are learned from shadow evidence. Any real-world amount and action remain entirely with the user in another app.

### 22.8 Replay and strategy acceptance

Tradovate exposes full-depth market replay and simulation, while warning that simulated results may differ from live results ([Tradovate simulation and replay](https://www.tradovate.com/platform/)). Trade One adopts the same separation and adds sport-state synchronization.

Every strategy must be replayed with:

- the canonical sport event stream;
- full available book/trade stream;
- provider and internal latency distributions;
- market suspensions and reopenings;
- actual fee and settlement rules;
- partial-fill and no-fill outcomes;
- stale/corrected sport events;
- strategy-specific signal lifecycle state.

Promotion gates by strategy/window:

- positive proper-score skill for the underlying forecast;
- positive net expectancy after conservative fills;
- positive median CLV and acceptable lower confidence bound;
- maximum drawdown within window policy;
- stable performance across teams, venues, game states, and months;
- no dependence on quoted-fill assumptions;
- sufficient turnover without pathological overtrading;
- live shadow confirmation before the strategy can be labeled production-grade.

### 22.9 Implementation changes caused by this research

Add these contracts/components to the staged build:

1. `MarketExitability` classification for user information.
2. `OpportunityPlaybook` signal-lifecycle state machine.
3. `StrategyTemplate` registry with entry/exit/invalidation predicates.
4. Sport DOM read model.
5. Optional user-entered paper-price and outcome tracking.
6. State stop, time stop, target, and trailing fair-value policies.
7. Daily loss, weekly loss, trailing drawdown, and manual lockout controls.
8. Event/book synchronized strategy replay.
9. Entry-to-exit episode metrics, including holding time and capital recycling.
10. Baseball inning 1–5/F3/F5, basketball Q1/Q2/H1, and football Q1/Q2/H1 route definitions.

These additions refine the “get in and get out” concept into a read-only product behavior: **publish a sharp, time-bounded opportunity; show its reference price, target, and invalidation; then expire or update it immediately as the sport state changes. The user independently decides what to do elsewhere.**

---

## 23. Final architecture lock

Trade One’s defensible advantage is not “AI picks.” It is the owned, replayable chain from exactly-timed evidence to two separately calibrated beliefs, then to a costed, latency-aware, risk-constrained decision.

The v1 commitment is:

```text
deterministic live state
    + calibrated sport distribution
    + calibrated market distribution
    + executable economics
    + explicit abstention and risk
    + complete replay/audit
```

Anything less is a demo. Anything claiming sub-second CV, frictionless fills, ground-truth market prices, or reinforcement learning before the required evidence exists is outside this blueprint.
