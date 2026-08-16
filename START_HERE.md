# Trade One — drag this folder into your coder

The complete package is in:

`trade-one-platform/`

Start with:

1. `trade-one-platform/README.md`
2. `trade-one-platform/docs/ARCHITECTURE.md`
3. `trade-one-platform/docs/FORMULA_INTEGRATION.md`
4. `trade-one-platform/docs/SWAPPING_COMPONENTS.md`
5. `trade-one-platform/config/trade-one.json`

Run the verification from inside `trade-one-platform`:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The ready-to-drag archive is also here:

`Trade One Modular Platform 0.1.0.zip`

The package is read-only with respect to sportsbooks, has separate pregame and
live pipelines, and is independent from M-31.

