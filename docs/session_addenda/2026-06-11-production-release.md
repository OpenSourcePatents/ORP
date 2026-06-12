<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Session addendum — 2026-06-11 — production release

Master fast-forwarded `27415fb..2f5f61e` (gui-core merged; trajectory-channels in its
ancestry) and pushed. Full pytest on the merged tip: **274 passed**. This addendum is
the release record: every commit hash of the session, the full-history secrets-scan
verdict, and the release smoke outputs.

## Every commit of this session (oldest first)

| Hash | Branch | Content |
|---|---|---|
| 711f428 | app-core | Task 0: contact email + absolute-path removal, sweep clean |
| d292fa2 | app-core | Task 1: BankSchedule.from_csv + 34 tests |
| bbf7938 | app-core | Task 1b: Gate-3 propagation bit-identity test (bit-identical) |
| 24ecbff | app-core | Task 2: sessions (save/load, SHA-256 hashes, refusal-over-repair) |
| 4a7f922 | app-core | Task 2b: load_session refuses frame: inertial with guidance to convert first |
| 70f6ab9 | app-core | Task 3: ORP CLI (run/vehicles/gates), entry point, UI wall test |
| 17f0972 | app-core | Phase 2: heading display wrap + README Quickstart |
| 27415fb | app-core | Phase 2: app-core session addendum → merged + pushed to master |
| 0ee3963 | trajectory-channels | Channels: CD, CL, L/D, alpha, specific force (RSS ≡ g-load bit-exact) |
| f2ae6fe | trajectory-channels | Plots: CD/CL vs Mach, q vs altitude, specific-force decomposition |
| 878cefa | gui-core | Shared extraction: orp/core/report.py + orp/gates/summary.py |
| 423282c | gui-core | GUI foundation: AppState + MainWindow skeleton + THE GUI WALL test |
| efe74d6 | gui-core | Vehicle panel (provenance-colored, display-only, reload) |
| 3a98bff | gui-core | Conditions panel (frame, warning, 3 schedule modes, run arming) |
| 5ff1685 | gui-core | Results panel, RunWorker QThread, gates panel |
| 59c4038 | gui-core | GUI test suite (9 tests incl. CLI/GUI byte-identity) |
| 2f5f61e | gui-core | gui-core addendum + gui packaging extra → merged + pushed to master |
| (this) | master | Production-release addendum |

## Secrets scan — full history, every object — VERDICT

Scope: `git cat-file --batch-all-objects` (400 objects: 171 blobs, 43 commits, 186
trees, 0 tags — reachable AND unreachable), every blob scanned raw with binary blobs
via ASCII-run strings-extraction (0 binary blobs exist), every commit object (message
+ headers, the `log -p` content being the blobs themselves), reflog, and local git
config. Patterns: AWS/GitHub/Slack/Google keys, JWTs, PEM/SSH private-key material,
basic-auth URLs, password/secret/token assignments, high-entropy strings (Shannon
> 4.3 over 844 candidates), emails beyond opensourcepatents@gmail.com, US-style phone
numbers, absolute private paths.

**No credentials of any kind, anywhere in history**: zero key/token/JWT/PEM/SSH/
basic-auth/password-assignment/phone-number hits. All 19 high-entropy flags
adjudicate to long documentation-path strings and snake_case identifiers (no
secrets). Remaining findings are the known, previously adjudicated (2026-06-10)
identity-correlation items, all fixed at tip and removable only by history rewrite:

1. `bedbugcharlie@gmail.com` in two historical `pyproject.toml` blobs and quoted in
   the 711f428 commit message that replaced it (tip carries only
   opensourcepatents@gmail.com).
2. `C:\Users\cjdow`-style paths in four pre-Task-0 blobs (reference/models.md,
   bridge doc/test, MSL source doc) — tip swept clean at 711f428.
3. `noreply@anthropic.com` Co-Authored-By trailer in root commit bc1a3dd (already on
   origin; later commits comply with the no-trailer rule) and quoted in the
   2026-06-10 addendum.
4. `noreply@github.com` web-flow committer identities on two historical GitHub-UI
   merge commits (public by nature).

## Release smoke — complete stdout

`python -m orp.cli run --vehicle apollo --planet earth --frame planet-relative
--bank-deg 60 --out release_smoke` (exit 0):

```text
Run complete: 4378 samples, terminated by GROUND_HIT at t=437.700 s.
Peak deceleration: 11.2043 g
Peak heat rate: 870448 W/m^2
Final state: altitude -5.5 m, velocity 75.95 m/s, latitude -1.23649 deg, longitude 9.62559 deg, flight-path angle -79.2518 deg, heading 242.1849 deg
Run provenance (weakest link): NOT_VALIDATED
Outputs written to release_smoke
```

`python -m orp.cli gates` (exit 0):

```text
GATE 3: Artemis I (Orion) skip entry  --  STATUS: NOT_VALIDATED
GATE: Stardust SRC ballistic entry  --  STATUS: NOT_VALIDATED
GATE 3 REPLAY: Artemis I digitized bank command, forward replay  --  STATUS: FAIL against the pre-registered tolerances; bank-sign convention NOT LOCKED; the gate stays NOT_VALIDATED
Summary: 0 of 3 gates validated, 3 scaffolded or honest-FAIL; all gates report their pinned expected statuses.
```

(The `release_smoke/` output directory is an untracked artifact and is not part of
the release; statuses are honest by design — nothing in this repo claims validation
it does not have.)
