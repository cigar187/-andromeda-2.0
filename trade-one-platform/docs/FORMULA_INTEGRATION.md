# Formula integration

The owner formula is a plugin, not pipeline code.

1. Copy `plugins/formulas/baseball_strikeouts_template.py` to a new versioned
   file.
2. Preserve `FORMULA_CONTRACT_VERSION = "1.0"` and `evaluate(context)`.
3. Replace only the proprietary math.
4. Add deterministic worked examples to `CONTRACT_EXAMPLES`.
5. Change the `formula.pregame` and/or `formula.live` factory settings.
6. Run the full test suite and `trade-one doctor`.
7. Train and evaluate a challenger; a successful load is not a promotion.

The loader hashes the complete formula file. A formula change therefore changes
lineage automatically and cannot silently reuse the old artifact identity.

Formula outputs:

- `projection`: expected count/value;
- `score`: formula-native quality score, not a probability unless documented;
- `features`: numeric values safe for downstream models;
- `flags`: eligibility/safety issues;
- `explanation_codes`: non-secret structured explanations.

The live and pregame slots can use different formulas or different versions of
the same formula.

