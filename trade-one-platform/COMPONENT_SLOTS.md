# Component slots

| Slot | Interface | Launch implementation | Independently swappable |
|---|---|---|---|
| `control` | `ControlEngine` | deterministic reference | yes |
| `sport.pregame` | `SportAdapter` | baseball | yes |
| `sport.live` | `SportAdapter` | baseball | yes |
| `formula.pregame` | `FormulaEngine` | strikeout template | yes |
| `formula.live` | `FormulaEngine` | strikeout template | yes |
| `brain.pregame` | `GroundTruthModel` | reference distribution | yes |
| `brain.live` | `GroundTruthModel` | reference distribution | yes |
| `market.pregame` | `MarketModel` | quote/no-vig reference | yes |
| `market.live` | `MarketModel` | quote/no-vig reference | yes |
| `calibrator.pregame` | `Calibrator` | identity/unfitted | yes |
| `calibrator.live` | `Calibrator` | identity/unfitted | yes |
| `grader.pregame` | `OpportunityGrader` | conservative rules | yes |
| `grader.live` | `OpportunityGrader` | conservative rules | yes |
| `repository.audit` | `AuditRepository` | JSONL | yes |
| `delivery` | `DeliveryAdapter` | no-op/read-only | yes |

The launch implementations marked `reference` or `unfitted` demonstrate the
end-to-end contract and are not claims of trained predictive performance.

