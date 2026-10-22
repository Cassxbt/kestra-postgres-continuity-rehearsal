# Observed wrong-endpoint refusal

Execution: `4BdqQoUkbbpS9ZEEbSIxNR`, Kestra OSS 2.0.6, October 21, 2026 Eastern.

The integration test expected publisher system ID `7699320173951602726` and subscriber ID `7699320173915201575` after rebuilding the disposable containers. The stored `inspect_publisher` task output was:

```text
{row:{baseline:"1:keep,2:before,3:remove",recovery:false,system_id:"7699320173915201575",barrier_lsn:"0/192F110",version_num:170009,cluster_name:"rehearsal_subscriber"},size:1}
```

Thus a successful SQL call and matching fixture data came from the wrong role. The flow failed at `require_expected_publisher`; `stop_old_publisher` and `promote_standby` never ran. Independent task-output recovery established the endpoint mismatch rather than inferring it from the error message.

Container recreation had reassigned addresses behind cached hostnames. The fixture now assigns a fixed address to each service and restarts Kestra once when changing its network. This is a reproducibility measure for this lab, not a claim that static IPs solve production identity or DNS problems. Identity and role checks remain in the flow.
