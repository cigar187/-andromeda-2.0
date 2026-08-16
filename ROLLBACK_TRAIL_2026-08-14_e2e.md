# ROLLBACK TRAIL — Andromeda 2.0 E2E Baseball Build

**Date:** 2026-08-14
**Authorization:** Robert's "one-time pass to work all the way through this end to end" directive
**Scope:** MLB pregame Andromeda cards displaying in the RN app on iPhone 17 Pro simulator, real Pinnacle + retail data via Rundown feed
**Rule 4 adherence:** No fallbacks, no duct tape. Missing engine fields are labeled honestly in-payload (e.g., "Real projection engines not yet wired; STATS stream reflects Pinnacle-derived edge only"). Placeholder team names are labeled as `team_<id>` — visibly not a real team name.
**Rule 9:** `sbc_engine_v5.py` md5 `9b066d6958ea708fc502020b9877b1f2` UNTOUCHED.
**A3:** New card assembler imports NO brain and NO formula engine — reads event log only.
**TiltBox:** ZERO touches. Verified — see "Isolation from TiltBox" section below.

---

## New files created (safe to delete for full rollback)

### Droplet (138.197.27.37)
| Path | Purpose | Rollback |
|---|---|---|
| `/opt/trade-one/andromeda_api/server.py` | Card assembler + HTTP server (port 8787, binds 0.0.0.0) | `pkill -f andromeda_api/server.py && rm -rf /opt/trade-one/andromeda_api/` |
| `/opt/trade-one/andromeda_api/server.log` | Server log | (same rm as above) |

### Local (Mac, TradeOnePackage/)
| Path | Purpose | Rollback |
|---|---|---|
| `TradeOneRN/src/theme/m31.js` | M31 color/space tokens (ported verbatim from `5thBase/src/theme/m31.js`) | `rm TradeOneRN/src/theme/m31.js && rmdir TradeOneRN/src/theme` |
| `TradeOneRN/src/config/api.js` | `API_BASE_URL` = `http://localhost:8787` (via SSH tunnel) | `rm TradeOneRN/src/config/api.js && rmdir TradeOneRN/src/config` |
| `TradeOneRN/src/components/AndromedaCard.jsx` | RN port of AndromedaCard (no LinearGradient/Ionicons deps) | `rm TradeOneRN/src/components/AndromedaCard.jsx` |
| `TradeOneRN/src/components/AndromedaFeed.jsx` | Sport-scoped feed screen; fetches `/api/andromeda/today?sport=<slug>` | `rm TradeOneRN/src/components/AndromedaFeed.jsx` |
| `TradeOnePackage/ROLLBACK_TRAIL_2026-08-14_e2e.md` | this file | `rm ROLLBACK_TRAIL_2026-08-14_e2e.md` |
| `/private/tmp/claude-501/.../scratchpad/andromeda_api_server.py` | source before ship (dup of droplet file) | ephemeral, auto-cleared |
| `/private/tmp/claude-501/.../scratchpad/expo_build.log` | expo build output | ephemeral |
| `/private/tmp/claude-501/.../scratchpad/metro.log` | metro server output | ephemeral |
| `/private/tmp/claude-501/.../scratchpad/start_server.sh` | droplet server-start helper | ephemeral |
| `/private/tmp/claude-501/.../scratchpad/m31_zip/` | unzipped m31-frontdoor (per Robert's one-time authorization) | ephemeral |

## Modified files (record the pre-edit state for revert)

### Local (Mac)
| File | Change | Rollback |
|---|---|---|
| `TradeOneRN/App.js` | Replaced entire `<Shell><Slate/><PlayerCard/><Feed/></Shell>` composition with `<Shell><AndromedaFeed sport={sport}/></Shell>`. Dropped imports for Slate, PlayerCard, Feed, adapter, T theme. Now imports M31Colors + AndromedaFeed. | Revert to git: `git -C TradeOneRN checkout HEAD -- App.js` (if repo). Manual: previous contents began with `import { useEffect, useMemo, useState } from "react";` and had ~95 lines including error panel + retry button. |
| `TradeOneRN/src/components/Shell.jsx` | Gutted chrome: removed SIGNAL DESK eyebrow, "Read the board." heading, subhead, pregame/live mode switch, T1 branding. Kept sport strip. Rebranded to "A2 / ANDROMEDA 2.0" with cyan mark and "Live · Pinnacle" pill. Now uses M31Colors instead of T theme. | Previous contents were ~91 lines; used `T` from `../theme.js`, had `MODES` and `pageHeading` block. |

### iOS build artifacts (Xcode DerivedData)
| Path | Change | Rollback |
|---|---|---|
| `~/Library/Developer/Xcode/DerivedData/TradeOne-aabrpcjgiaqzwfendnyngzozppxz/` | Fresh Debug-iphonesimulator build from this session | Auto-managed by Xcode; delete DerivedData or rebuild |
| `TradeOneRN/ios/Pods/` | Pods reinstalled by `expo run:ios` | Rebuild pods via `cd TradeOneRN/ios && pod install` |
| iPhone 17 Pro sim (UDID `CA0B3CE4-CE3B-4C9F-8B85-5D73F5B008BE`) — `com.tradeone.rn` | New TradeOne.app replaced prior install (baked packager port = 8082) | `xcrun simctl uninstall CA0B3CE4-CE3B-4C9F-8B85-5D73F5B008BE com.tradeone.rn` |

## Untouched files (verified)

| File | md5 pre / post |
|---|---|
| `TradeOnePackage/sbc_engine_v5.py` | Aug 3 baseline (not touched) |
| Droplet `/opt/trade-one/sbc_engine_v5.py` | `9b066d6958ea708fc502020b9877b1f2` (Rule 9 baseline, unchanged) |
| `TradeOnePackage/trade-one-platform/plugins/feeds/rundown_props.py` | `d146eef28d158edf6be650c962970137` (from earlier socketize pass, unchanged this pass) |
| `TradeOnePackage/trade-one-platform/config/feeds.json` | Unchanged this pass |
| `TradeOneRN/src/components/Slate.jsx`, `PlayerCard.jsx`, `Feed.jsx` | Left in place, unmodified — now orphaned imports; safe to delete later or keep for reference |
| `TradeOneRN/src/data/adapter.js`, `mockData.js` | Left in place, unmodified — orphaned; safe to delete later |
| `TradeOneRN/src/theme.js` | Left in place, unmodified — no longer imported by App.js or Shell.jsx |
| `TradeOneRN/package.json`, `Podfile`, `Podfile.lock` | Unchanged (no new npm/pod deps added — used only what was already installed) |
| `TradeOneRN/ios/TradeOne.xcodeproj/*` | Unchanged (project structure, bundle ID, target name all preserved) |

## Running processes (this session)

| Process | Where | PID (at time of writing) | Purpose | Stop cmd |
|---|---|---|---|---|
| `python3 /opt/trade-one/andromeda_api/server.py` | Droplet | 160104 | Card API on 0.0.0.0:8787 | `ssh root@138.197.27.37 pkill -f andromeda_api/server.py` |
| `ssh -f -N -L 8787:localhost:8787 root@138.197.27.37` | Mac | 28381 | Tunnel Mac:8787 → droplet:8787 | `pkill -f "ssh.*-L 8787"` |
| `npx expo start --port 8082 --dev-client` | Mac | 30295 | Metro for TradeOne on 8082 | `pkill -f "expo start --port 8082"` |

## Isolation from TiltBox — verified

- TiltBox's Metro (PID 65738, cwd `/Users/rac187/TiltBox`) on port **8081** was NOT touched, NOT killed, NOT contacted.
- TradeOne's Metro on port **8082** is a separate `node` process with cwd `/Users/rac187/Documents/TradeOnePackage/TradeOneRN` (authorized folder).
- The `Tilt` app on the sim (PID 68888) remains installed and still talks to its Metro on 8081.
- Both apps can coexist; each has its own Metro on its own port, no shared state.
- Zero reads/writes to `/Users/rac187/TiltBox` or `/Users/rac187/Documents/axiom` at any point in this session.

## Data-honesty notes (Rule 4 disclosures)

Every field on each card is either real data from Pinnacle/retail books via the Rundown feed, or an explicitly labeled placeholder. Nothing is fabricated silently.

| Field | Source | Honest label |
|---|---|---|
| `pitcherName` | Rundown `participant_name` in `prop_snapshot` | real |
| `team` / `opponent` | Rundown team_id (renders as `team_57`) | **placeholder** — no team-name mapping wired yet; visibly not a real team name |
| `statCategory` | `market_stat` neutral name from adapter | real (`Strikeouts`) |
| `line` | Pinnacle main-line from `prop_snapshot` | real |
| `direction` / `conviction` / `edgeScore` / `edgeBand` | Computed from Pinnacle 2-price no-vig | real math |
| `booksAgreeNum` / `booksAgreeDen` / `booksLabel` | Count of DK/BetMGM/HardRock/FanDuel `money_move_snapshot` rows where `price_delta_american < 0` on the leaning side | real (den is 4 — the money-move book set) |
| `kProj` | Line + `(no_vig_over - 0.5) * 2.0` — market-inferred estimate | **market-inferred** — explicitly stated in the `brief` field: "Real projection engines (V5B / M31 tribunal) not yet wired; STATS stream reflects Pinnacle-derived edge only." |
| `drivers[]` | Inferred from where the loudest signal lives (money-move vs. line edge). If money agrees ≥2 books AND fill ≥0.3 → MONEY-LED; else STATS-LED. | **inferred**, not from real engines. Brief discloses this. |
| `regressionWarn` | Always false | **not wired** — no data source yet |
| `simFloor` / `simMedian` / `simCeiling` | Absent from payload | **omitted** — no SIM engine wired; card's sim tile row hides when the fields are absent |
| `stats.fill` | `edgeScore / 100` (from Pinnacle no-vig) | real Pinnacle math, but labeled as "Pinnacle-derived edge only" in brief until real STATS engine wires in |
| `money.fill` / `money.read` | Sum of abs `price_delta_american` from money-move books | real |
| `news` (stream) | Absent from payload | **omitted** — no news engine wired; row hides when absent |
| `isAlert` | Bool: `edgeScore >= 60 OR (num_agree >= 3 AND money_fill >= 0.5)` | derived |

## Live proof (from the running sim at 1:32 PM)

Rendered cards visible on iPhone 17 Pro sim:
- Walbert Urena · Strikeouts 4.5 · ▲ OVER · conviction moderate · 0.63 · K PROJ 4.75 · EDGE 25 MODERATE · BOOKS 0/4 no agree
- Shane Bieber · Strikeouts 4.5 · ▲ OVER · moderate · 0.62 (top of visible fold)
- Michael King · Strikeouts 3.5 · ▲ OVER · thin · 0.59 · K PROJ 3.68 · EDGE 18 LOW · BOOKS 2/4 leaning
- Gerrit Cole · Strikeouts 5.5 · ▼ UNDER (purple rail) · thin · 0.58 · K PROJ 5.33 · EDGE 17 LOW · BOOKS 1/4 early move
- 16 more cards below (20 total for tonight's MLB slate)

Under-the-hood proof:
- `curl http://localhost:8787/health` → `{"ok": true, "date": "2026-08-14"}`
- `curl http://localhost:8787/api/andromeda/today?sport=mlb` → 20 verdicts, alerts sorted first, edge-desc
- Sport strip tap between Baseball/Basketball/Football/Hockey/Soccer works; non-MLB shows honest "coming soon" empty state

## To reboot from a clean state next session

```bash
# 1. Start card server on droplet
ssh root@138.197.27.37 'nohup python3 /opt/trade-one/andromeda_api/server.py > /opt/trade-one/andromeda_api/server.log 2>&1 & disown'

# 2. Open SSH tunnel Mac → droplet
ssh -f -N -L 8787:localhost:8787 root@138.197.27.37

# 3. Start Metro for TradeOne (leave TiltBox's on 8081 alone)
cd /Users/rac187/Documents/TradeOnePackage/TradeOneRN
LANG=en_US.UTF-8 npx expo start --port 8082 --dev-client &

# 4. Launch app on already-installed sim
xcrun simctl launch CA0B3CE4-CE3B-4C9F-8B85-5D73F5B008BE com.tradeone.rn
```

## Additions after initial ship (same session, same Rule 4 discipline)

### 1. Starter-only filter in the card assembler (per Robert 2026-08-14 mid-turn directive)
- Added `if not team_id: continue` guard in `assemble_cards_for_sport()` inside `/opt/trade-one/andromeda_api/server.py`
- Rationale documented inline: not a Rule 4 skip, a product-defined filter. The row is in the bus; we're choosing not to card it. Sportsbooks price relievers and position players occasionally; only announced starters (pitcher_home / pitcher_away per Rundown event) are real bet targets.
- The Rundown adapter already sets `team_id` ONLY when `participant_id` matches the event's announced starter, so the filter uses that existing signal cleanly.
- To disable in the future: add `?starters_only=false` query param and thread it through. Suggested socket, not built this pass.
- Today's count unchanged (20 → 20) because all 20 Pinnacle prop lines happened to be for starters.
- Rollback: remove the `if not team_id: continue` block and the surrounding comment in `_emit_for_market` (`server.py` line ~215).

### 2. Release build replacing Debug on the sim
- Rebuilt via `npx expo run:ios --configuration Release --device "iPhone 17 Pro"` from `TradeOneRN/`.
- Metro dev server no longer required at runtime — JS is bundled into the .app itself.
- Removes React Native dev inspector overlay ("Inspect / Perf / Network / Touchables" bar and "Nothing is inspected" tooltip).
- Fresh install path: `~/Library/Developer/Xcode/DerivedData/TradeOne-aabrpcjgiaqzwfendnyngzozppxz/Build/Products/Release-iphonesimulator/TradeOne.app`
- Bundle ID unchanged: `com.tradeone.rn`
- To rebuild Debug (if you want live-reload back): `LANG=en_US.UTF-8 npx expo run:ios --device "iPhone 17 Pro"` (default Debug config)
- To keep Release running: no server needed on your end. `xcrun simctl launch CA0B3CE4-CE3B-4C9F-8B85-5D73F5B008BE com.tradeone.rn` after sim boot.
- Still-required backend: droplet server on 8787 + SSH tunnel Mac:8787 → droplet:8787 (both listed in "Running processes" above).

### 3. Pinnacle-as-current-engine honest disclosure (per Robert observation on Andrew Alvarez disagreement)
- The "verdict" in Andromeda 2.0 right now is Pinnacle's own no-vig fair on the market line — NOT a real projection engine, NOT M31, NOT V5B/DNO.
- When TiltBox/Andromeda-1 disagrees with Andromeda-2.0 on Alvarez (TiltBox says OVER, A2 says UNDER 54%), that is: "TiltBox's real engine vs Pinnacle sharp market."
- The M31-vs-E0 architecture test Robert wants requires M31 wired as middleware AND a projection engine wired behind M31. Not done this pass. Documented as "next work" below.

### 4. Team-name enrichment on the bus (adapter v0.4.0 → v0.5.0)
- `plugins/feeds/rundown_props.py`: pulled `name` field from Rundown's `teams_normalized`, added `team_name` and `opponent_name` to `_emit_row` signature and to the payload's top level. Adapter version bumped 0.4.0 → 0.5.0.
- `/opt/trade-one/andromeda_api/server.py` assembler: prefers `payload.team_name` / `payload.opponent_name` when present; falls back to `team_<id>` honestly if not (protects older events).
- Rotated today's event files to `.pre-team-names` on droplet; re-ran adapter with the Andromeda key — emitted 1,325 events (40 Pinnacle + 1,285 money-move) all with real team names.
- Restarted card server; cards on sim now render "Los Angeles vs Texas" instead of "team_57 vs team_60".
- Honest limitation: Rundown provides city names only, not team mascots. LA/NY/Chicago same-city ambiguity remains — a `team_id → mascot` lookup is a small follow-up when the operator wants it (defer per Robert direction).

## Next work (out of scope this pass, tracked for later)

- Wire team-name mapping (Rundown provides team names in `teams_normalized` — add to adapter, remove `team_<id>` placeholder)
- Wire M31 consumer to sit between event log and card assembler (M31 as middleware socket — `feedback_wire_first_perfect_later`)
- Wire V5B (`sbc_engine_v5.py`) as a real projection engine driving `kProj` — replaces market-inferred estimate
- Wire real STATS / NEWS engines behind the stream fills
- Wire SIM engine → populate `simFloor` / `simMedian` / `simCeiling`
- Baseball tab is the only live one; other sports show honest "coming soon" until wired
- Rename discussion (deferred per Robert): `trade_one` → `andromeda2` naming sweep across paths, packages, iOS project

### 5. M31 consumer field-shape fix (2026-08-14 close-out — Change 1 of three-part E2E pass)
- File: `/opt/trade-one/trade-one-platform/src/trade_one/m31_consumer.py`
- Pre-md5: `7daac7dbf6be78df963110ada1a1ec3e`
- Post-md5: `a677e1a1053e0e3abf55a2c149cc4142`
- Added explicit named transform `_pair_prop_events()` + `paired_prop_to_envelope()` reconciling the per-side prop_snapshot events (adapter shape) to the paired IntelligenceEnvelope ControlPlane requires. Consumer reads event-log JSON only; no adapter import (M1 preserved).
- Verification: 40 prop_snapshot events → 20 pairs → 14 accepted / 6 quarantined ("as_of after event_start" — games already started; pregame-only mandate honored). Admission rate 0% → 70%.
- Runtime note: must be invoked with `/opt/trade-one/backtest/venv/bin/python3` because `codex_control_engine/__init__.py` eagerly imports torch.
- Rollback: scp pre-md5 version back from a backup, or manually revert to the pre-2026-08-14 shape (single per-event `prop_event_to_envelope` reading top-level `line`/`over_odds`/`under_odds`).
- Event log trail: task_started `evt_20260814T195642423390_e730d8fa1b09` → task_completed `evt_20260814T200547552092_90aa2114d0cf` in `/opt/trade-one/data/events/`.

### 6. Honest driver chip (2026-08-14 close-out — Change 2 of three-part E2E pass)
- File: `/opt/trade-one/andromeda_api/server.py`
- Pre-md5: `2bdc5958ede64fa0c72f52e816af9661`
- Post-md5: `4527be37245a79b0afacada64e8a2599`
- Before: `DRIVER · STATS-LED` shown on every card even though no stats engine is wired (projection was Pinnacle no-vig throughout). Card displayed a claim provably false against its own brief text ("market-inferred projection").
- After: default `DRIVER · SHARP MARKET` (truthful — Pinnacle no-vig is the driver). `DRIVER · MONEY-LED` + `MARKET AGREES` shown only when retail money moved with real conviction (`num_agree >= 2` AND `money_fill >= 0.3`). Secondary money chips (`MONEY QUIET / EARLY MOVE / LEANING`) reflect real book state.
- Verification: 0 cards show STATS-LED on the live feed. Sim screenshot proof captured this session.
- Rollback: same file as Change 7 (both live in server.py) — restore pre-md5 to undo both together.

### 7. No-vig dead-zone flag (2026-08-14 close-out — Change 3 of three-part E2E pass)
- File: `/opt/trade-one/andromeda_api/server.py` (same file as Change 6)
- Pre-md5: `2bdc5958ede64fa0c72f52e816af9661` (shared with Change 6)
- Post-md5: `4527be37245a79b0afacada64e8a2599` (shared with Change 6)
- Config-driven band via env vars: `ANDROMEDA_NO_EDGE_LOWER` (default 0.48), `ANDROMEDA_NO_EDGE_UPPER` (default 0.52). Overridable at server-start time, no soldered numbers.
- When Pinnacle `no_vig_over ∈ [lower, upper]`: card carries `no_edge_dead_zone: true` and gets two loud indicators through existing RN-rendered fields — (a) conviction override `COIN FLIP · no edge · 0.51`, (b) warn-tone chip prepended to drivers `⚠ COIN FLIP · NO EDGE`.
- Verification: 5 dead-zone cards flagged today — Chase Burns (0.481), Brandon Pfaadt (0.492), Chris Sale (0.512), Matthew Liberatore (0.490), Jackson Jobe (0.494). Every qualifying card gets the flag — no skipping.
- Rollback: same file as Change 6 — restoring pre-md5 removes both simultaneously.
- Explicit deferred follow-up: dedicated colored badge in the RN app for even louder visual treatment (Mac RN file edit — deferred pre-close-out; requires separate authorization).

### 8. Scout: TestFlight-readiness inventory (2026-08-14 close-out — read-only)
- No file changes. Full report captured in `/Users/rac187/Documents/5thbase/AXIOM_BUILD_LOG.md` under section "Andromeda 2.0 E2E close-out + TestFlight-readiness scout".
- Key facts:
  - 5thbase: Expo/EAS-managed under Expo account `cigar187`, bundle `com.fifthbase.app`, App Store Connect ASC App ID `6744708557`, EAS projectId `cd58b7a3-6a21-41ca-abdc-ec5c0cdb5814`, version 1.0.0 build 6, distribution cert + profile held on Expo servers (cloud-managed).
  - TradeOnePackage/TradeOneRN: bundle `com.tradeone.rn`, NO eas.json, NO EAS projectId, NO ASC App ID — needs `eas init` + new App Store Connect record OR (Path B chosen post-scout) bundle-ID rename to `com.fifthbase.app` to reuse 5thbase's slot.
  - Endpoint: bound at `0.0.0.0:8787` on droplet (world-open plain HTTP), no domain, no TLS, no auth. Real-device use needs HTTPS + domain + `EXPO_PUBLIC_ANDROMEDA_API` baked at build time + auth token.

### 9. Public HTTPS + Bearer auth for andromeda_api (2026-08-15 — Path B Step 2)
- File: `/opt/trade-one/andromeda_api/server.py`
- Pre-md5: `4527be37245a79b0afacada64e8a2599`
- Post-md5: `80cd0cd060dac9394f2e0f3d9b417ea3`
- Added `_check_bearer_auth()` (hmac.compare_digest, /api/* gated), main() `sys.exit(1)` if `ANDROMEDA_API_TOKEN` not set. Server now binds `127.0.0.1:8787` (loopback; caddy fronts public HTTPS).
- New system packages: caddy 2.6.2 installed via apt.
- New system files: `/etc/caddy/Caddyfile`, `/root/.andromeda_api_token` (chmod 600, root-only, token value NEVER written to any doc/log/payload).
- Public URL: `https://138-197-27-37.nip.io` (nip.io wildcard DNS → droplet public IP 138.197.27.37).
- TLS: Let's Encrypt auto-obtained on caddy start.
- Rollback: (a) restore server.py to pre-md5 (removes auth), (b) `systemctl stop caddy && systemctl disable caddy && apt purge -y caddy && rm -rf /etc/caddy`, (c) `rm /root/.andromeda_api_token`. Server will need `ANDROMEDA_API_TOKEN` unset in start command to allow open-access again (currently the main() gate refuses to start without it).
- Event log: task_started `evt_20260815T065455826891_2dbcdab4467f`.

### 10. RN app Path B config (2026-08-15 — Path B Step 3)
- Files:
  - `TradeOnePackage/TradeOneRN/app.json` — pre-md5 `667379d64c45742d1fd851309eab057a` → post-md5 `4f8bfb8ab4be8b3bd355d1998260f1e7` (rename revert to 5thBase per operator; slug fifthbase; version 1.0.0; bundle com.fifthbase.app; buildNumber 7; owner cigar187; extra.eas.projectId cd58b7a3-6a21-41ca-abdc-ec5c0cdb5814)
  - `TradeOnePackage/TradeOneRN/eas.json` — NEW file (post-md5 `b12c200de07a5f3206460fdbc2bf36cf`) — patterned on 5thbase's, production iOS Release + build image + ascAppId=6744708557
  - `TradeOnePackage/TradeOneRN/src/config/api.js` — pre-md5 `8e5109f6e37b0bad8856c36542b759f4` → post-md5 `20aece08a87999da40d1cdf91464587e` (added `API_TOKEN` from `EXPO_PUBLIC_ANDROMEDA_API_TOKEN` env; default empty — server 401s cleanly if unset)
  - `TradeOnePackage/TradeOneRN/src/components/AndromedaFeed.jsx` — pre-md5 `6d2c40a45eda7ba38e57b01b9687aaff` → post-md5 `1bd6f9afe954049d16def32352644d37` (adds `Authorization: Bearer ${API_TOKEN}` header when token present; updated dev-tip hint text)
- EAS env vars registered for project `@cigar187/fifthbase` in `production` environment:
  - `EXPO_PUBLIC_ANDROMEDA_API=https://138-197-27-37.nip.io` (plaintext visibility)
  - `EXPO_PUBLIC_ANDROMEDA_API_TOKEN=***** (masked)` (sensitive visibility — EXPO_PUBLIC_ can't be "secret" per EAS)
- Rollback: restore all four files to pre-md5s (record above). Delete `TradeOnePackage/TradeOneRN/eas.json`. Delete EAS env vars via `eas env:delete production --name EXPO_PUBLIC_ANDROMEDA_API_TOKEN` and same for `_API`.
- Notes:
  - Bundle change from `com.tradeone.rn` to `com.fifthbase.app` means the currently-installed dev app on the sim (com.tradeone.rn) is orphaned. Rebuild + install replaces it with a `com.fifthbase.app` build that will overwrite any 5thbase install on the same sim (fine for tester dev, but be aware).
  - Shared EAS project: 5thbase source tree also points at `cd58b7a3-...`, so its builds see the same env vars now. Its code doesn't reference `EXPO_PUBLIC_ANDROMEDA_API*`, so no functional impact.

### 11. Pre-upload verify (2026-08-15 — Path B Step 4, verify only, no code change)
- Method: Release-configuration simulator build on fresh iPhone 17 Pro Max sim (UDID `C6605D8B-066D-4896-A21D-9B2C3D756476`).
- No code changes this step. Only artifact side-effects:
  - `TradeOnePackage/TradeOneRN/ios/` regenerated via `expo prebuild --clean --platform ios` (bundle now `com.fifthbase.app`; folder name is now `5thBase.xcodeproj` / `5thBase.xcworkspace`). Pre-Path-B ios/ dir backed up to `ios.backup-pre-pathb/`. Rollback: `rm -rf ios && mv ios.backup-pre-pathb ios && cd ios && pod install`.
  - New app installed to Pro Max sim (bundle `com.fifthbase.app` v1.0.0 build 7). Rollback: `xcrun simctl uninstall C6605D8B-066D-4896-A21D-9B2C3D756476 com.fifthbase.app`.
  - Xcode DerivedData: `~/Library/Developer/Xcode/DerivedData/5thBase-bbbulizvmztxkzhcmajgwzglrtzi/`. Rollback: delete the folder (Xcode regenerates).
- Result: PASS — 30 real MLB cards flowing through public HTTPS + Bearer auth end-to-end. Same JS bundle EAS will produce for device.

### 12. Git init + Path-B EAS build (2026-08-15 — Path B Step 5.1/5.2)
- `TradeOnePackage/TradeOneRN/.git/` — new git repo (rollback: `rm -rf .git && rm .gitignore` to un-repo). Identity set to `cigar187 <info@cigar187.com>`.
- `TradeOnePackage/TradeOneRN/.gitignore` — new file (see Step 5.1 in AXIOM_BUILD_LOG for contents).
- EAS build shipped: build ID `d1762c50-ead7-45a2-9444-de4c7c09123a`. Artifact at https://expo.dev/artifacts/eas/PVtVm41mf8RkVJIXbs9b95m0yr9Xr1mMiiEUS9u2kBU.ipa
- Rollback (build): can be discarded via Expo dashboard — build artifacts on EAS Cloud only, nothing installed locally except via TestFlight.

### 13. TestFlight submit FAILED — pending Apple error detail (2026-08-15 — Path B Step 5.3)
- No file changes; submission failure is Apple-side.
- Two submissions attempted, both failed:
  - `72b3ee21-9368-44e3-b187-8e984226731d`
  - `8e6df896-c357-4a62-b853-926f24db2334`
- Awaiting operator to read the specific error from the Expo submission dashboard for a targeted fix.

### 14. TestFlight submit succeeded (2026-08-15 — Path B Step 5.3 fix + resubmit)
- Root cause: `eas.json:submit.production.ios.ascAppId` was `6744708557` (stale — copied from 5thbase's own eas.json which also has this stale value). Real ASC App ID for `com.fifthbase.app` is `6760734873` per Apple's own submission-error response.
- Fix: `TradeOnePackage/TradeOneRN/eas.json` — `ascAppId: 6744708557` → `6760734873`. No rebuild required (submit uses ascAppId; build already valid).
- Submission ID: `0684bd62-d606-443f-8008-f114f757774f`. Status: uploaded to ASC, Apple processing in progress.
- TestFlight destination: https://appstoreconnect.apple.com/apps/6760734873/testflight/ios (same slot as production 5thbase testers).
- FYI for Robert: 5thbase's own `eas.json` still has the stale `ascAppId: 6744708557`. He should update to `6760734873` before his next `eas submit` for 5thbase. Not touched this pass per Rule 8 read-only on 5thbase.

### 15. Daily 9:30am ET Rundown auto-poll (2026-08-15 — Path B bonus step)
- New droplet files (all inside `/opt/trade-one` + system systemd units):
  - `/opt/trade-one/andromeda_api/daily_poll.sh` (md5 `aef94039035c09a2e8bcea0c4164fa7b`, chmod +x) — script the timer calls; reads Rundown API key from `/root/.andromeda_rundown_key` (never echoed).
  - `/etc/systemd/system/andromeda-rundown-poll.service` — oneshot service, calls the script above.
  - `/etc/systemd/system/andromeda-rundown-poll.timer` — `OnCalendar=*-*-* 09:30:00 America/New_York`, `Persistent=true`.
- Systemd enabled; next fire Sat 2026-08-15 13:30 UTC (= 9:30am EDT); auto-adjusts for EST/EDT via tz spec (no annual maintenance).
- Dry-run verified: emitted 1902 events for the current slate.
- Rollback: `systemctl disable --now andromeda-rundown-poll.timer && rm /etc/systemd/system/andromeda-rundown-poll.{service,timer} && rm /opt/trade-one/andromeda_api/daily_poll.sh && systemctl daemon-reload`.

### 16. Export-compliance Info.plist key (2026-08-15 — post-ship fix, future-builds only)
- File: `TradeOnePackage/TradeOneRN/app.json`
- Added `expo.ios.infoPlist.ITSAppUsesNonExemptEncryption: false`
- Effect: eliminates the "App Encryption Documentation" dialog Apple shows on every new TestFlight build. Applies to build 8+ (build 7 unblocked by answering the dialog directly in ASC console).
- Rationale: app uses only standard HTTPS (React Native fetch → iOS URLSession → OS-level TLS), which is US-export-exempt. No custom crypto in code.
- Rollback: remove the `infoPlist` block from app.json. Reverting reintroduces the dialog on subsequent builds.

### 17. Rundown token-burn fix — affiliate_ids_filter (2026-08-15)
- File: `TradeOnePackage/TradeOneRN/../trade-one-platform/plugins/feeds/rundown_props.py`
- Version: 0.6.0 → **0.7.0**
- Post-md5: `3b6882501b8bfd6cd329eeeb26acd513`
- Change: added `affiliate_ids_filter` setting (default `[3, 19, 22, 23, 28]` = Pinnacle + 4 money-move books). Passed to Rundown as `affiliate_ids=` URL param. Reduces per-call response payload ~60% (467KB → 188KB).
- Rule 4: not a skip. We ask Rundown for fewer books; we emit everything Rundown returns.
- Rollback: revert file to pre-md5; the previous adapter fetched all affiliates and emitted them.
- To disable filtering (fetch every affiliate again): add `"affiliate_ids_filter": []` to `feeds.json:feeds.rundown_props.settings`.
- Cost projection at steady-state: 188KB × 1 poll/day × 30 days = 5.6MB/month. Well under 1% of 25M-token quota.

**Operator discipline note:** manual dev-time polls of the Rundown adapter are the primary token drain, not the daily cron. Today's slate is already in `/opt/trade-one/data/events/prop_snapshot/YYYY-MM-DD.jsonl` — use that for card assembler dev instead of re-polling Rundown.

### 18. Pregame-only display filter — stale-cards fix (2026-08-15)
- File: `/opt/trade-one/andromeda_api/server.py`
- Pre-md5: `3b6882501b8bfd6cd329eeeb26acd513` (from earlier this session)
- Post-md5: `c632bf772b47ab250ef1fba235c03dea`
- Added `_is_pregame(event_start)` — returns True if game starts more than N minutes from now (default 10, overridable via `ANDROMEDA_LOCK_MINUTES_BEFORE_START` env var). Cards render only when true.
- Root cause: Rundown's `/sports/3/events/<UTC_date>` straddles US ET evenings (UTC 00:00 = 8pm EDT prior day), so today's UTC response includes last night's late EDT games. Fix is display-side; the bus retains every event.
- Verification: 29 mixed → 20 pregame-only cards after fix. Stale names (Kirby, Lambert, Lugo, Rocker, Yamamoto, Gasser, Roupp, Freeland, G. Rodriguez, Jump) all correctly excluded.
- Rollback: revert file to pre-md5; assembler will resume rendering all Pinnacle-quoted props regardless of event_start.
