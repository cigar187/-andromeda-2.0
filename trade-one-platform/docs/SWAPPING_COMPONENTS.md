# Swapping components safely

## Procedure

1. Implement the relevant abstract interface.
2. Declare a component manifest and compatible contract major.
3. Provide a factory accepting a settings dictionary.
4. Add contract tests using frozen request fixtures.
5. Add golden-output or tolerance tests where appropriate.
6. Run replay and shadow evaluation.
7. Change one configuration slot in a challenger environment.
8. Verify `doctor`, health, lineage, latency, and rollback.
9. Promote only after the component-specific gates pass.

Example brain swap:

```json
"brain.pregame": {
  "factory": "owner_new_brain.plugin:create",
  "settings": {"artifact_uri": "gs://...", "version": "9.0.0"}
}
```

No pipeline, API, UI, formula, database schema, or live brain change is required
if the replacement honors contract major 1.

## Contract evolution

- Backward-compatible fields increment the minor contract version.
- Breaking changes increment the major version.
- During a major migration, deploy explicit v1/v2 translators at the boundary.
- Never make a component infer which contract it received.
- Retain old artifacts and configuration for instant rollback.

## Independence tests

The test suite proves that:

- pregame and live slots can use different brains;
- a formula can be swapped without changing pipeline code;
- incompatible contract majors fail at startup;
- mode mixing is rejected;
- future pregame data is rejected;
- component lineage changes when a plugin changes.

