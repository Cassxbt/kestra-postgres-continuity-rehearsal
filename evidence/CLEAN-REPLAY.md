# Clean local replay — October 22, 2026

**Result: 10 tests passed in 371.426 seconds; command exit code 0.** Nine tests exercise real Kestra/PostgreSQL integration across ten executions. One separate local HTTP regression test exercises a connection closing during service startup; it is not another database-integration scenario.

- [Full successful command output](clean-replay.txt)
- [Credential-free proof and actual runtime versions](clean-replay-proof.json)
- [Earlier integration review and scope](TEST-REPORT.md)

## What was fresh

Source commit `5e848f2` was cloned into a separate directory with `git clone --no-hardlinks`. The checkout was clean before and after the run. No `.env` or ignored raw execution files were copied. The documented `make test` command generated new credentials, initialized a new Kestra metadata database and storage volume, imported the flow, bootstrapped/reset the three disposable target databases and ran the tests.

To preserve the original evidence volumes on the same Docker engine, the harness supplied this external Compose override through `COMPOSE_FILE`:

```yaml
volumes:
  kestra-db:
    name: kestra-rehearsal-release-20261022-metadata
  kestra:
    name: kestra-rehearsal-release-20261022-storage
```

Only those two volume names changed. The fixture's tasks, endpoints, credentials generator, database setup and assertions were unmodified. The original metadata/evidence volumes were retained. Images were already cached and pinned by digest; this was not a fresh image-download test or a replay on another machine.

## Failures found and fixed

1. [First cold attempt](cold-start-attempt-1.txt): the runtime closed an HTTP connection while starting. The readiness helper did not retry that exception, so zero integration tests ran. A focused HTTP-server regression reproduced `RemoteDisconnected` before the fix and passed after adding `ConnectionError` to the transient startup errors. Authentication/validation errors are not silently swallowed by that retry.
2. [Second attempt](cold-start-attempt-2.txt): the Kestra service exited during startup. Container inspection showed exit code 1 and `OOMKilled=false`. The service log reported `Failed connecting to Kestra controller (DEADLINE_EXCEEDED)` and a call starting after its deadline. The fixture now gives the worker/controller connection a bounded five-minute allowance, permits five minutes for API readiness and sizes the serial lab to two worker threads/two JVM-visible processors with a 1.5 GiB heap. The underlying engine has approximately 4 GiB RAM.

The worker timeout property and its default 30-second deadline are defined in [Kestra's configuration source](https://github.com/kestra-io/kestra/blob/develop/worker-controller/src/main/java/io/kestra/controller/config/WorkerControllersConfiguration.java). These are fixture settings, not a claimed upstream code fix. The fresh replay after the changes completed successfully. This does not establish which resource adjustment alone would have been sufficient.

## Observable outcome

Successful execution: `2fwyVKOjJB7JzugVeyhfXL`. The tests independently checked old-publisher shutdown, standby promotion, source and subscriber records `1|keep`, `2|after`, `4|inserted`, the enabled subscription's new endpoint, and unchanged subscription OID `16392` and origin ID `1`.

Missing-slot execution: `6ArHQQfag2ZmZRAdKejwr1`. The actual inspection output showed correct system ID, recovery role and replay readiness, with `slot_ready=false`. It failed at the intended gate before shutdown/promotion.

The remaining cases exercised denied consent, wrong expected identities, missing/disabled subscription, wrong data with the same row count, unreachable standby and a repeated run after promotion. Each refused at the asserted task and never emitted a continuity receipt.

Actual fresh-runtime versions: Kestra 2.0.6, JDBC PostgreSQL plugin 2.3.0, Docker plugin 1.7.0; PostgreSQL image 17.9. Images are pinned; plugin versions are reported observations. All unsupported production/concurrency/recovery claims in the original report remain unsupported. The two failed attempts are retained, with personal checkout paths replaced by `<checkout>`.

## Publication status

The companion is public. [Upstream PR #4791](https://github.com/kestra-io/blueprints/pull/4791) was approved and merged on October 23, 2026. This acceptance does not establish a prize or extend the tested scope. An independent practitioner replay remains unverified.
