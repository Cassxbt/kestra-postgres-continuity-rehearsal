import unittest

from lab_support import bootstrap, command, compose, eventually, install_flow, run_flow, sql, task_output


def assert_failed_at(test, execution, expected, preceding=()):
    test.assertEqual('FAILED', execution['state']['current'], execution['id'])
    states = {task['taskId']: task['state']['current']
              for task in execution.get('taskRunList', [])}
    test.assertEqual('FAILED', states.get(expected), (execution['id'], states))
    for task_id in preceding:
        test.assertEqual('SUCCESS', states.get(task_id), (execution['id'], states))
    for task_id in ['stop_old_publisher', 'promote_standby', 'continuity_evidence']:
        test.assertNotIn(task_id, states)


class RehearsalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_flow()

    def test_switchover_preserves_existing_subscriber_and_exact_data(self):
        before = bootstrap()
        execution = run_flow({
            'allow_disposable_switchover': True,
            'expected_publisher_system_id': before['system_id'],
            'expected_subscriber_system_id': before['subscriber_id'],
        })
        self.assertEqual('SUCCESS', execution['state']['current'], execution['id'])
        self.assertEqual('f', sql('standby', 'SELECT pg_is_in_recovery();'),
                         'A no-op workflow must not pass the continuity test')
        self.assertEqual('false', command(['docker', 'inspect', '--format',
                                          '{{.State.Running}}',
                                          'kestra-rehearsal-publisher']))
        self.assertEqual('1|keep\n2|after\n4|inserted', sql(
            'subscriber', 'SELECT id,value FROM rehearsal_items ORDER BY id;'))
        self.assertEqual('1|keep\n2|after\n4|inserted', sql(
            'standby', 'SELECT id,value FROM rehearsal_items ORDER BY id;'))
        self.assertEqual('t', sql('subscriber', "SELECT subenabled AND "
            "subslotname='rehearsal_sub' AND subconninfo LIKE 'host=standby %' "
            "FROM pg_subscription WHERE subname='rehearsal_sub';"))
        self.assertEqual(before['subscription_oid'], sql(
            'subscriber', "SELECT oid FROM pg_subscription WHERE subname='rehearsal_sub';"))
        self.assertEqual(before['origin_id'], sql(
            'subscriber', 'SELECT roident FROM pg_replication_origin;'))
        task_ids = [task['taskId'] for task in execution.get('taskRunList', [])]
        self.assertLess(task_ids.index('stop_old_publisher'), task_ids.index('promote_standby'))
        task_output(execution, 'continuity_evidence')
        repeated = run_flow({
            'allow_disposable_switchover': True,
            'expected_publisher_system_id': before['system_id'],
            'expected_subscriber_system_id': before['subscriber_id'],
        })
        assert_failed_at(self, repeated, 'inspect_publisher', ['require_consent'])
        self.assertEqual('1|keep\n2|after\n4|inserted', sql(
            'subscriber', 'SELECT id,value FROM rehearsal_items ORDER BY id;'))

    def test_missing_standby_slot_refuses_before_any_promotion(self):
        before = bootstrap(sync_slots=False)
        self.assertEqual('0', sql('standby', "SELECT count(*) FROM pg_replication_slots "
                                  "WHERE slot_name='rehearsal_sub';"))
        execution = run_flow({
            'allow_disposable_switchover': True,
            'expected_publisher_system_id': before['system_id'],
            'expected_subscriber_system_id': before['subscriber_id'],
        })
        assert_failed_at(self, execution, 'standby_not_ready',
                         ['inspect_publisher', 'inspect_subscriber', 'inspect_standby'])
        standby = task_output(execution, 'inspect_standby')['row']
        self.assertEqual(before['system_id'], standby['system_id'])
        self.assertEqual('rehearsal_standby', standby['cluster_name'])
        self.assertIs(True, standby['recovery'])
        self.assertIs(True, standby['caught_up'])
        self.assertIs(False, standby['slot_ready'])
        self.assertEqual('t', sql('standby', 'SELECT pg_is_in_recovery();'))
        self.assertEqual('f', sql('publisher', 'SELECT pg_is_in_recovery();'))
        self.assertEqual('1|keep\n2|before\n3|remove', sql(
            'subscriber', 'SELECT id,value FROM rehearsal_items ORDER BY id;'))
        self.assertNotIn('stop_old_publisher',
                         [task['taskId'] for task in execution.get('taskRunList', [])])


class RehearsalSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_flow()
        cls.before = bootstrap()

    def inputs(self, **overrides):
        values = {
            'allow_disposable_switchover': True,
            'expected_publisher_system_id': self.before['system_id'],
            'expected_subscriber_system_id': self.before['subscriber_id'],
        }
        return values | overrides

    def assert_refused_without_stopping_publisher(self, inputs, expected):
        execution = run_flow(inputs)
        preceding = {
            'consent_missing': [],
            'unexpected_publisher': ['require_consent', 'inspect_publisher'],
            'unexpected_subscriber': ['inspect_publisher', 'require_expected_publisher',
                                      'inspect_subscriber'],
            'inspect_standby': ['require_expected_publisher', 'require_expected_subscriber'],
        }
        assert_failed_at(self, execution, expected, preceding[expected])
        if expected != 'inspect_standby':
            self.assertEqual('t', sql('standby', 'SELECT pg_is_in_recovery();'))
        self.assertEqual('true', command(['docker', 'inspect', '--format',
                                         '{{.State.Running}}',
                                         'kestra-rehearsal-publisher']))

    def test_denied_consent_cannot_stop_or_promote(self):
        self.assert_refused_without_stopping_publisher(
            self.inputs(allow_disposable_switchover=False), 'consent_missing')

    def test_wrong_publisher_identity_cannot_stop_or_promote(self):
        self.assert_refused_without_stopping_publisher(
            self.inputs(expected_publisher_system_id='0'), 'unexpected_publisher')

    def test_wrong_subscriber_identity_cannot_stop_or_promote(self):
        self.assert_refused_without_stopping_publisher(
            self.inputs(expected_subscriber_system_id='0'), 'unexpected_subscriber')

    def test_missing_expected_subscription_cannot_stop_or_promote(self):
        sql('subscriber', 'ALTER SUBSCRIPTION rehearsal_sub RENAME TO unexpected_sub;')
        try:
            self.assert_refused_without_stopping_publisher(self.inputs(), 'unexpected_subscriber')
        finally:
            sql('subscriber', 'ALTER SUBSCRIPTION unexpected_sub RENAME TO rehearsal_sub;')

    def test_disabled_subscription_cannot_stop_or_promote(self):
        sql('subscriber', 'ALTER SUBSCRIPTION rehearsal_sub DISABLE;')
        try:
            self.assert_refused_without_stopping_publisher(self.inputs(), 'unexpected_subscriber')
        finally:
            sql('subscriber', 'ALTER SUBSCRIPTION rehearsal_sub ENABLE;')

    def test_unexpected_data_cannot_pass_by_matching_only_row_count(self):
        sql('publisher', "UPDATE rehearsal_items SET value='unexpected' WHERE id=1;")
        try:
            eventually(lambda: sql('subscriber',
                        "SELECT value FROM rehearsal_items WHERE id=1;") == 'unexpected')
            self.assert_refused_without_stopping_publisher(self.inputs(), 'unexpected_publisher')
        finally:
            sql('publisher', "UPDATE rehearsal_items SET value='keep' WHERE id=1;")
            eventually(lambda: sql('subscriber',
                        "SELECT value FROM rehearsal_items WHERE id=1;") == 'keep')

    def test_unreachable_standby_is_failure_not_a_ready_result(self):
        compose('stop', 'standby')
        try:
            self.assert_refused_without_stopping_publisher(self.inputs(), 'inspect_standby')
        finally:
            compose('up', '-d', '--wait', 'standby')
        self.assertEqual('t', sql('standby', 'SELECT pg_is_in_recovery();'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
