// Endpoint config for Andromeda 2.0.
//
// PRODUCTION (TestFlight / App Store): EAS build injects these at build time via
// eas.json:build.production.env → EXPO_PUBLIC_ANDROMEDA_API. The auth token is
// injected as an EAS secret (EXPO_PUBLIC_ANDROMEDA_API_TOKEN) — never checked in.
//
// DEV (Metro/simulator): if the operator wants live cards in dev, they must set
//     export EXPO_PUBLIC_ANDROMEDA_API=https://138-197-27-37.nip.io
//     export EXPO_PUBLIC_ANDROMEDA_API_TOKEN=$(ssh root@138.197.27.37 cat /root/.andromeda_api_token)
// before `npx expo start`. Otherwise the app falls back to the SSH-tunnel default
// on localhost:8787 (which also requires the token env var — server refuses open access).
//
// Rule 4: no fallback to open access. If the token is empty, the fetch will send
// no Authorization header and the server will return 401 — the AndromedaFeed's
// existing "Backend unreachable" empty state handles this cleanly.
const configuredUrl = process.env.EXPO_PUBLIC_ANDROMEDA_API?.trim();
const configuredToken = process.env.EXPO_PUBLIC_ANDROMEDA_API_TOKEN?.trim();

export const API_BASE_URL = configuredUrl || "http://localhost:8787";
export const API_TOKEN = configuredToken || "";
