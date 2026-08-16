# Integrating Trade One with another application

Trade One is a read-only intelligence service. The host application sends a
canonical request and receives a versioned response. It does not import model
classes or formula files.

## Recommended boundary

Run Trade One as its own container/process and call:

- `POST /v1/intelligence/pregame`
- `POST /v1/intelligence/live`
- `GET /health`

The request examples in `examples/` are the integration fixtures. The host app
should persist these response fields:

- `contract_version`
- `trace_id`
- `as_of`
- `state_revision`
- complete `components` lineage
- opportunity status and expiry

Never display a cached `READY` response after `expires_at` or after the host app
observes a newer state revision.

## Local-process option

Python hosts may import `load_pipelines()` and `request_from_dict()`, but a
service boundary is preferred because it allows the Trade One runtime and the
host app to upgrade independently.

## Read-only guarantee

The API intentionally has no sportsbook authentication, wager, order, submit,
cancel, or execution endpoint. The host app may offer `COPY`, `PIN`, `PAPER`,
and `DISMISS` actions without changing Trade One's intelligence contract.

## Compatibility

Pin the contract major. A host supporting `1.x` must reject a future `2.x`
response until a migration adapter is installed. Component versions can change
without affecting the host because component lineage is data, not an API shape.

