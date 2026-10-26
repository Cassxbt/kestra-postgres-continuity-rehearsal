# Independent replay and usefulness review

This guide is for an engineer evaluating whether the rehearsal is reproducible and useful. No independent practitioner replay is claimed yet. A failed run or a finding that the drill adds no value is useful feedback.

## What you are evaluating

A disposable PostgreSQL publisher is stopped, its physical standby is promoted, and the existing logical subscription is redirected. The tests independently query the databases to verify the expected insert, update and delete results and retained subscription/origin identity. A missing failover slot must cause refusal before shutdown or promotion.

The [blueprint was merged](https://github.com/kestra-io/blueprints/pull/4791). Acceptance is not evidence of production safety or adoption. The supported scope is one quiescent three-row fixture, one table and one subscriber; see [boundaries](README.md#boundaries).

## Before running

- Read [Run it](README.md#run-it), including the Docker socket access and reset behavior. Use a disposable development setup, never an existing database environment.
- You need Git, Make, Python 3.9+, Docker and Compose. The original run used approximately 4 GiB of Docker memory and about 10 GiB of image space. This is an observed setup, not a universal resource guarantee.
- Port 18080 and subnet `172.29.77.0/24` must be available. The fixed `kestra-rehearsal` container/volume names must not belong to another deployment. Run only one copy per Docker engine.
- Prefer your own machine and an unmodified checkout. If you need assistance or modify anything, record it; that does not invalidate the feedback.

## Replay

```sh
git clone https://github.com/Cassxbt/kestra-postgres-continuity-rehearsal.git
cd kestra-postgres-continuity-rehearsal
git checkout 9fd36fc805d9201dc89c8b378fe1d51f1a5d97e7
git rev-parse HEAD
make test
```

This pins the reviewed executable package. This guide was added after that revision, so keep this page open while testing. The test command generates local credentials, starts the fixture, and resets its disposable databases between scenarios. First startup and image downloads may take several minutes.

**Expected:** ten tests complete with `OK` and exit code zero. Nine are real integration tests spanning ten Kestra executions; one is a local startup regression. Individual Kestra executions deliberately print `FAILED` for refusal scenarios. Those tests must still report `ok`; a suite-level error/failure is not success.

Record the actual result, even if it differs. If setup fails, capture the command, error and any assistance required before attempting changes. Do not restart individual destructive tasks or point the flow at real infrastructure.

After the run, stop the fixture without deleting its evidence:

```sh
make stop
```

## Inspect the proof

The [integration tests](tests/test_rehearsal.py) assert database state independently of the flow's receipt:

| Case | Required observation |
| --- | --- |
| Successful transition | Old publisher stopped; standby promoted; both new publisher and subscriber contain `1|keep`, `2|after`, `4|inserted`; subscription OID and replication-origin ID match their pre-run values |
| Missing standby slot | Identity, recovery and replay checks pass; slot readiness is false; failure occurs at `standby_not_ready`; shutdown and promotion do not run |
| Other refusals | Denied consent, wrong identities, missing/disabled subscription, incorrect data and unreachable standby fail at the asserted task without a continuity receipt |
| Repeat after promotion | Old-publisher inspection fails; no second promotion or new receipt |

Your execution IDs and database identifiers will differ from the author's [saved replay](evidence/CLEAN-REPLAY.md). The full suite resets state between cases, so its final database contents are not a substitute for the per-case assertions. Published author evidence is reference material, not evidence that your run succeeded.

## Report back

Copy this template into your reply, or open an issue in this companion repository. Partial reports are welcome.

```text
Reviewer / relevant PostgreSQL experience (optional):
Date, OS/architecture, Docker/Compose/Python versions, Docker memory:
Commit tested:
Own machine and fresh checkout? Existing lab volumes?
Command run, total tests, final result and exit code:
Success and missing-slot test outcomes / execution IDs:
Assistance, edits or deviations from the README:
First confusing or broken step:

Would this fit an actual promotion/upgrade rehearsal you perform? Which one?
How do you check downstream logical-subscriber continuity today?
Does this add anything to that process, or duplicate existing tooling?
What would prevent you using it? What is the most important missing check?

May your feedback be quoted publicly? Yes/no; preferred attribution:
```

Share only reviewed, redacted excerpts. Do not upload `.env`, passwords, connection strings or unreviewed raw execution dumps. Public attribution is optional; anonymous feedback can still be useful if its method is described accurately.

We distinguish a documentation review, an independent replay, a relevant operational use case, and actual adoption. None automatically proves the others. A successful lab replay does not establish production fencing, zero loss with concurrent writers, arbitrary topology support or safe recovery from a partially completed promotion.
