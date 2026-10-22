# PostgreSQL continuity experiment

The tests exercise a real Kestra flow and real PostgreSQL 17.9 instances. No service response is mocked. This is a disposable manual-switchover lab, not a general HA controller.

The initial no-op flow must fail the success assertion: the standby is not promoted and the subscriber never receives post-switch mutations. That red run establishes that a successful Kestra state alone cannot satisfy the test.

After implementation, the success test independently checks that the old publisher is stopped, the candidate is promoted, the existing subscription OID and origin are retained, and exact expected records arrive. A second run must refuse the already changed topology. The negative test removes required slot readiness and must fail before stopping or promoting either server.

Additional tests cover wrong target identity, unreachable endpoint, missing/disabled subscription, denied execution consent, and unexpected baseline data. Each refusal must reach its intended failed task after the relevant successful inspections, with no shutdown, promotion or continuity receipt. The missing-slot test retrieves actual inspection outputs to exclude unrelated readiness failures. The lab owns every container and named volume under the fixed `kestra-rehearsal` Compose project. Database ports are not published; the Kestra UI binds localhost only. Runtime passwords are generated into ignored `.env`, not flow YAML.

No tests below establish safety for arbitrary production clients, global traffic fencing, multiple subscribers, or concurrent topology changes. Those claims require a different operational contract.
