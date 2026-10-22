# Reviewed integration result

Update: [the October 22 clean local replay](CLEAN-REPLAY.md) passed ten tests after fixing cold-start setup failures. This document preserves the earlier nine-test reviewed result and its scope.

Run: October 21, 2026 Eastern / October 22 UTC. **9 tests passed in 138.743 seconds, spanning 10 actual Kestra executions.** These establish the stated disposable-lab behavior, not production HA, operator demand or a predicted award.

Authoritative log: [integration-reviewed-2.txt](integration-reviewed-2.txt). Machine-readable, credential-free summary: [reviewed-proof.json](reviewed-proof.json). Earlier attempt logs remain available, including the runtime rejection of catalog-only `extend` metadata; they are not the final result.

## Environment

- Kestra OSS 2.0.6; image pinned by digest in `compose.yaml`.
- PostgreSQL 17.9, Debian Bookworm; image pinned by digest.
- JDBC PostgreSQL plugin 2.3.0; Docker plugin 1.7.0, observed from the runtime API and saved in [plugin-versions.json](plugin-versions.json).
- Docker Desktop engine 29.7.2 on this macOS machine.
- Four private PostgreSQL services: publisher, physical standby, logical subscriber, and separate Kestra metadata database. Only the Kestra UI binds to loopback.
- An isolated, exclusively owned, quiescent three-row fixture. Superuser permissions, one publication/subscription/table, complete initial readiness. No concurrent application writer.

## Observations

| Scenario | Execution ID | Result established |
|---|---|---|
| Missing synchronized logical slot | `6IKdDJlsoMRWdCybC8ldV6` | Failed at `standby_not_ready`; identity, role and replay checks were true, `slot_ready=false`; no shutdown/promotion |
| Real controlled switchover | `qjJx2OgMeTtmgf3Z7R3Ee` | SUCCESS; stopped old publisher, promoted standby, existing subscriber received exact changes |
| Repeat after successful switchover | `51joKjUw13lqAcNCLLxDYO` | Failed querying the stopped publisher; no second promotion or fabricated receipt |
| Consent denied | `7OzIwQU9sF5HpQ3M0fqCq9` | Failed at `consent_missing` before mutation |
| Disabled subscription | `3DJna3JOYiR4jQsoD7pGgE` | Failed at `unexpected_subscriber` before mutation |
| Expected subscription absent | `5LS6jKXLnHHJTnndHqgEKB` | Failed at `unexpected_subscriber` before mutation |
| Same row count, wrong contents | `27AidosWN7u8C4hBuV5p1F` | Failed at `unexpected_publisher`; row count alone cannot satisfy the baseline |
| Standby unreachable | `DBsOOpfiwHePwwYXvioXx` | Failed in `inspect_standby`; no shutdown/promotion, recovery verified after restart |
| Wrong expected publisher identity | `4ygoCGa0vZIIJileHPlSN` | Failed at `unexpected_publisher` before mutation |
| Wrong expected subscriber identity | `1PDrfJPfF8FGhH6NYPY3j` | Failed at `unexpected_subscriber` before mutation |

The missing-slot inspection was retrieved through Kestra's execution expression-evaluation API. It explicitly records `recovery=true`, `caught_up=true`, the expected system ID and cluster name, and `slot_ready=false`. This isolates the fault rather than accepting any failed readiness check.

The successful execution's source **and** subscriber independently contained `1|keep`, `2|after`, `4|inserted`; the original row 3 was absent. The subscription remained enabled, used `host=standby` and the expected slot, and retained OID `16392` and replication-origin ID `1`. The emitted evidence agrees with those independent reads. Shutdown precedes promotion in the execution graph.

## Adversarial review and fixes

An independent read-only reviewer found that the original negative tests accepted arbitrary failures and did not independently exclude promotion. The revised tests assert the intended failed leaf, preceding successful tasks, absence of shutdown/promotion/receipt tasks, and actual recovery state. They also check the promoted source's data and subscription retargeting. Origin lookup now names the expected subscription's origin rather than selecting an arbitrary origin. Recovery guidance begins at subscriber disablement, the first mutation.

The reviewer rechecked those fixes and found no remaining critical or important issue within the stated lab scope. This is a review of implementation and assertions, not an independent replay on a second machine.

## Claims deliberately left open

Only missing-slot failure has direct slot-fault injection evidence. Unsynced, temporary and invalidated slot predicates exist but have not each been independently injected. Wrong expected IDs were injected; a complete different-cluster/same-slot fixture was not. Permission-obscured catalogs, incomplete table copies, changing topology, concurrent writes, interrupted promotion, automatic recovery and individual resumed tasks remain unproven or outside this fixture's contract.

The repeat-run result proves refusal in the observed stopped-publisher state. It does not prove general idempotency or safe partial-failure recovery. The Docker stop is an observed local shutdown, not global production traffic fencing. Any failure from `pause_subscriber` onward requires inspection and a fixture reset.

The catalog metadata meets its documented nine-field/eight-section structure; runtime import omits the final `extend` block because the Flow API rejects catalog metadata. A publicly usable companion-fixture reference, another engineer's replay, latest upstream review checks and maintainer usefulness feedback remain outstanding. The candidate is **runtime-validated locally, not submission-ready**.
