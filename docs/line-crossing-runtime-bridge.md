# Line Crossing runtime bridge (App #32)

Authoritative inputs: ne301 #84 comment 6229932486 (frozen browser-level typed
MessagePort bridge v1, shared with the Host implementation) and the App #32
`ght-contract`. This document is the App-owned HOW for that frozen WHAT: the
production counting UI (NEAPP05 unsigned admin-installed package) consumes
Host-granted capabilities only through this adapter and fails closed on every
deviation. It does not re-freeze wire semantics, grant Host API passthrough,
or claim any device/cross-site property that has not been executed.

## Production entry

`apps/line-crossing/ui/src/main.tsx`:

- top-level document (`window.parent === window`) or opaque origin
  (`self.origin === 'null'`): `unavailableCapabilities`; the adapter is not
  armed at all;
- framed document: `createRuntimeCapabilities(connectHostBridge())` passed to
  the unchanged `LineCountingModule` from App #25.

The test fixture entry (`tests/line-crossing-ui/src/test-main.tsx`) keeps its
own `createTestCapabilities` injection. The production entry never imports test
code and never defines `__lineCrossingTest`; the UI suite asserts this against
the production build output.

## Bridge v1 usage (App side)

- Handshake: exactly one `HELLO` on `ne301.sidecar.bridge.v1`, accepted only
  from `event.source === window.parent`, trusted event, non-opaque sender
  origin, exactly one `MessageChannel` port, exact channel field. The App
  never treats its own URL, `app_id` strings, or a nonce as authorization;
  real admission stays with Host #83/#84.
- Envelope: `protocol/type/seq/grant_id/identity` on every message; strict
  exact-field validation for `HELLO/GRANT/REQUEST/RESULT/EVENT/REVOKE`;
  `identity` is the full 10-field tuple; `app_id` must equal
  `line-crossing` before any grant is adopted.
- Requests: `request_id:u32` + `seq:u32` strictly increasing, ops restricted
  to the GRANT whitelist
  (`snapshot.read, config.read, config.apply, counters.reset,
  report-policy.read, report-policy.apply, video.open, video.close,
  enable.read, enable.apply, live.subscribe, live.unsubscribe`), at most 4
  concurrent pending, 10 s deadline, 16 KiB encoded-size bound in both
  directions. Timeouts resolve `UNKNOWN`; late `RESULT`s for expired requests
  are dropped; nothing is committed without a cross-checked `APPLIED`.
- Inbound discipline: inbound `seq` must strictly increase; replays/duplicates
  are dropped; identity or grant_id mismatch, malformed envelopes, oversized
  messages and unknown types revoke the session (`REVOKE` is final; the port
  is closed; a new session requires an iframe reload).
- Events: `EVENT` payloads carry `stream/stream_seq` plus optional
  `GAP/STALE/REVOKE` status; a sequence rollback or gap marks live
  capabilities unavailable until a Host resync; live data is bounded
  (<= 100 events / 100 tracks / 64 points per track) and strictly validated.
- Grant lifecycle: a GRANT with `expires_at_ms <= Date.now()` is rejected.
  The active grant is checked again immediately before a REQUEST is sent and
  when each RESULT or EVENT is consumed. An expired request is not sent and
  returns `UNAVAILABLE`; a pending request whose RESULT arrives after expiry
  resolves `UNKNOWN`; an EVENT after expiry is dropped. Expiry clears the
  active grant, resolves other pending requests as `UNKNOWN`, and marks the UI
  unavailable while keeping the channel ready for a fresh GRANT. A fresh GRANT
  with the same handshake identity and a newer sequence can restore
  authorization; stale sequences are dropped and identity changes revoke.

## App-side payload schemas

Result payloads are validated field-by-field; any deviation fails closed for
that capability instead of partial rendering:

- `snapshot.read` APPLIED: `{ session_generation, config_generation, config
  (schema-1 candidate), status, stats? }` → `app` + `stats` capabilities.
  Missing `stats` stays honestly unavailable.
- `report-policy.read/apply` APPLIED: `{ session_generation, generation,
  config { mqtt_enabled, webhook_enabled, backlog_capacity } }` →
  `hostPolicy` (camelCase `sessionGeneration` on the UI side).
- `enable.read` APPLIED: `{ session_generation, value }` → `businessEnable`;
  `UNAVAILABLE` is surfaced verbatim as a real unavailable (App #30 producer
  is not implemented and must never appear enabled).
- `video.open` APPLIED: `{ url (ws:/wss: only), session_generation,
  expires_at_ms, grant_id }` → bounded media grant; `release()` is App-local,
  emits unavailable and fires `video.close`.
- Writes carry the current generation (`expected_config_generation`,
  `expected_generation`) and commit only when the echoed session/generation
  reconcile with the request; otherwise the UI shows `UNKNOWN`/`CONFLICT` and
  never optimistic-commits.

## Evidence and reproduction

From the repository root, offline:

```sh
bash tests/line-crossing-ui/run.sh
```

runs, in order: offline dependency install, the vite production + fixture
builds, the UI offline browser suite (Google Chrome via Playwright,
`--offline`), then the runtime suite `tests/line-crossing-runtime/run.sh`:

- `tests/line-crossing-runtime/contract.test.mjs` — Node-only protocol and
  adapter tests (validation, seq/replay, pending cap, deadlines, revocation,
  payload fail-closed, generation cross-checks);
- `tests/line-crossing-runtime/browser.test.mjs` — real-Chrome fixture with a
  Host broker page, the production build in the sandboxed
  App iframe and a hostile sibling iframe; covers authorized use (writes,
  counters reset, media open/close under revocation), absent/wrong/limited
  grants, opaque origin, seq rollback, oversize, late-ACK after revoke,
  stale-session echo, sibling forgery, cross-site cookie/DOM/storage/admin
  denial, same-origin widening and the same-site port-only cookie leak.
  These are fixture-level lab cases about the fixture's cookie and admin
  endpoint, not claims about target Host policy; the approved deployment
  model is the NEAPP05 unsigned admin-installed App.

Executed with: Node v22.22.3, Google Chrome 155.0.8059.80 (headless, Playwright
chromium.launch), ffmpeg-generated baseline H264 fixture.

## Explicit NOT_RUN / unavailable by design

- Host #84 real resource service, permission granting and broker (the fixture
  broker is test code in this repository, not Host production code).
- #88/#101 Host policy engine and App #30 native Enable producer remain
  unavailable by design. App #27's v4 entry now arms its live producer and
  publishes through `live_publish`; the fixture boundary is described below
  and does not prove production admission.
- Production Host resource service/session grant, target hardware, and device
  acceptance remain NOT_RUN.
- Real camera/stream, target-board memory/network/flash/integration, device
  acceptance, production signing keys, production downloads/recording export
  (FileSaver `saveAs` remains failed; the anchor fallback requires a
  Host download token, and no recording download PASS is claimed).
- Target deployment DNS/TLS, camera and Host site topology; the `.test` resolver
  mapping is local to this Chrome fixture. Opaque-origin positive operation
  (Worker/importScripts/H264 under opaque origin).

## App #27 — LVN4 native live producer

Host #104 F8–F10 ([freeze comment 6258637748](https://github.com/harryhua-ai/ne301/issues/104#issuecomment-6258637748))
remain the wire authority. App #27 converts the real tracker and bus crossing
facts into LVN4 kind1 event batches and kind2 full-replacement track
snapshots. It leaves v3 reports, totals, `report_seq`, and queued delivery
history unchanged.

### App source path

- `apps/line-crossing/app/lc_lvn4.{h,c}` implements the frozen 48-byte header,
  kind1 16-byte records, kind2 track snapshots, GAP accounting, resync flags,
  and fail-closed sequence and capacity handling.
- `apps/line-crossing/app/lc_bus.{h,c}` exposes the additive observer where
  tracker facts are known. In the v4 entry, trusted bus events reach the
  observer; Paused, corrupt, storage-restricted, and fatal states return
  before it. Idle processing has no observer call and retains #30's window
  close gate.
- `apps/line-crossing/app/lc_app_entry_v4.c` binds the observer to the producer
  and adapts producer output to the real `api->live_publish` callback. The v4
  Make target compiles `lc_lvn4.c`. A `-3` callback result fails the live
  capability closed, preserves consumed packet/source watermarks, marks loss
  unknown, and requires resynchronization.

The accepted App #30 base is integrated at exact commit
`a1b93322ae010356a6293421a137564fc0e23664`. The `lc_bus.c` merge resolution
keeps #30 STOPPING handling and FRAME receive timestamp, and retains its
`business_state_trusted` checks on FRAME processing and idle window close.
The observer is called only after the FRAME/GAP trust gate. The v4 entry
drives the producer gate from restored and updated schema3 state: ENABLED
opens it, PAUSED holds it, and UNKNOWN/corrupt/restricted/fatal state closes
it. The joint fixture checks Paused/UNKNOWN suppression, preserved business
state, and `RESYNC_REQUIRED` after resume.

### Production entry and capability boundary

The frozen 64-byte v4 function table exposes `live_publish(const void *,
uint32_t)` but does not expose the Host session generation,
`live_publish_max`, or `live_track_max`. The v4 production entry now creates a
bounded local entry epoch, arms `lc_lvn4` with the 9008-byte/64-track profile,
binds the bus observer, and routes produced packets through the real
`api->live_publish` callback. This is the active App producer path; it removes
the earlier claim that the production entry does not arm or publish.

The entry test exercises that path with a fixture callback and a real pinned
Host parser/read implementation, but its Host authorization boundary is
simulated. It does not establish production admission, a production
Host session grant, or device behavior. Package/admission behavior is covered
separately by the unsigned NEAPP05 admission suites; they do not combine
admission with the App entry/tracker callback path.

### Joint test and byte fixtures

Run from the repository root:

```sh
bash tests/line-crossing-live/run_tests.sh
```

The script compiles App producer code with Host parser sources archived
read-only from exact Host candidate
`4c1c0d7ec5bc8ae18fae4ca5a31f0699b7c5895b`. The C test passes producer
buffers directly to `app_host_live_ingest`, then checks Host read/cursor and
snapshot results. The suite regenerates every fixture and its SHA-256
manifest at runtime into `tests/line-crossing-live/work/evidence/`; no
fixture bytes are committed to the repository.

| Fixture | Producer output | Host result |
| --- | --- | --- |
| `kind1-event-batch.bin` | kind1 event batch | ACCEPT |
| `kind1-source-gap.bin` | kind1; `through_seq=64`, total 64, source gap 48 | ACCEPT; read state GAPPED and watermarks 64/64/48 |
| `kind2-tracks-64x16.bin` | kind2, 64 tracks × 16 points, 9008 bytes | ACCEPT under matching test caps 9008/64 |
| `kind2-zero-track.bin` | kind2 full replacement with zero tracks | ACCEPT; Host snapshot read returns zero tracks |

The test identity is `trusted-test-owner` / `line-crossing`, session 7001,
with test caps 9008/64. These are fixture inputs, not production
admission. Negative and boundary cases are individually asserted:

| Case | Expected/result |
| --- | --- |
| 9008-byte packet with test caps 312/1 | bounded event packet ACCEPT; oversized snapshot REJECT (`ERR_LENGTH`) |
| Old session generation after TBS identity changes and session 7103 binds | REJECT (`ERR_GENERATION`); Host status reports new TBS context |
| Legacy `NFC3` bytes passed to LVN4 ingest | REJECT (`ERR_HEADER`) |
| Host event ring overrun / slow reader | packets ACCEPT; read is GAPPED with `host_dropped_events > 0` |
| Session ended, then ingest attempted | REJECT (`ERR_UNBOUND`) |
| App callback returns `-3` for unavailable/revoked capability | producer fails closed, preserves consumed packet/source watermarks, marks loss unknown, and requires resynchronization |
| Wrong TBS on packet bytes | UNAVAILABLE at parser layer: LVN4 bytes do not carry TBS; Host admission must bind trusted identity before parser use |

Host #91 is an in-flight delivered candidate, not ACCEPTED. This joint result
is based on that delivered source; final same-byte reconciliation remains
subject to Host-side review.

### Verification results

| Check | Result |
| --- | --- |
| LVN4 wire producer | PASS, 1502 checks |
| Bus and producer regression | PASS, 100 checks |
| Host #91 parser/read/cursor joint fixture | PASS, 610 checks |
| App #30 schema3 Paused/UNKNOWN gate fixture | PASS, 19 checks |
| App #30 source-pinned joint matrix | PASS: Host 77 + 592, cross-owner 67, Enable 204, v4 entry 15; full AC4 production gate NOT_RUN |

The regression evidence pins the App code revision exercised by the tests.
The exact documentation Candidate SHA is recorded by the PR #39 `ght deliver`
snapshot because that SHA is created after the evidence files are committed.

### Acceptance layers and NOT_RUN

- Signed-format parser acceptance is a parser result against pinned delivered
  Host source and test identity. It does not prove a production Host session
  grant.
- The production v4 App entry arms the producer with a bounded local epoch and
  9008/64 profile and routes packets through `live_publish`. The 79/0 entry
  fixture exercises that callback path with simulated Host authorization; it
  is not production admission or a device result. No production keys
  or device were used.
- Web/UI integration is NOT_RUN and outside this native producer result;
  #108/#113 work is not represented here.
- Host #91 remains unaccepted; final Host-side same-byte reconciliation is
  NOT_RUN.
- Hardware/NPU feed, target memory/CPU budget, production admission, and
  device acceptance are NOT_RUN.
