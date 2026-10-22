import base64
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / 'flows/postgres-subscriber-continuity-rehearsal.yaml'
FLOW_ID = 'postgres-subscriber-continuity-rehearsal'
NAMESPACE = 'company.rehearsal'
BASE_URL = 'http://127.0.0.1:18080'
ENV = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines())


def command(args, data=None, timeout=120):
    result = subprocess.run(args, input=data, text=True, capture_output=True,
                            cwd=ROOT, timeout=timeout)
    if result.returncode:
        message = result.stderr + result.stdout
        for value in ENV.values():
            message = message.replace(value, '[REDACTED]')
        raise RuntimeError(f'{args[0:3]} failed: {message}')
    return result.stdout.strip()


def compose(*args, **kwargs):
    return command(['docker', 'compose', '--profile', 'replica', *args], **kwargs)


def sql(service, statement):
    return compose('exec', '-T', service, 'psql', '-X', '-qAt', '-v',
                   'ON_ERROR_STOP=1', '-U', 'lab', '-d', 'rehearsal', data=statement)


def eventually(check, timeout=90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(1)
    raise AssertionError(f'Condition did not become true in {timeout}s; last={last!r}')


def api(method, path, data=None, content_type='application/json'):
    auth = base64.b64encode(
        f"lab@example.invalid:{ENV['LAB_ADMIN_PASSWORD']}".encode()).decode()
    request = urllib.request.Request(BASE_URL + path, data=data, method=method,
                                     headers={'Authorization': 'Basic ' + auth,
                                              'Content-Type': content_type})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        details = error.read().decode()[:1500]
        error.close()
        raise RuntimeError(f'Kestra {method} {path}: {error.code} '
                           + details) from error


def wait_for_api(timeout=300):
    def available():
        try:
            return api('GET', '/api/v1/configs')
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return None

    return eventually(available, timeout=timeout)


def install_flow():
    wait_for_api()
    # The catalog consumes extend; Kestra's runtime Flow schema does not.
    source = FLOW.read_text()
    body = source.split('\nextend:\n', 1)[0].encode()
    validation = api('POST', '/api/v1/main/flows/validate', body, 'application/x-yaml')
    if validation and any(item.get('constraints') or item.get('outdated')
                          for item in validation):
        raise AssertionError(f'Flow validation failed: {validation}')
    try:
        return api('POST', '/api/v1/main/flows', body, 'application/x-yaml')
    except RuntimeError as error:
        if 'already exist' not in str(error).lower() and '409' not in str(error):
            raise
        return api('PUT', f'/api/v1/main/flows/{NAMESPACE}/{FLOW_ID}', body,
                   'application/x-yaml')


def run_flow(inputs=None):
    boundary = 'kestra-rehearsal-inputs'
    body = b''
    for key, value in (inputs or {}).items():
        value = str(value).lower() if isinstance(value, bool) else str(value)
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                 f'\r\n\r\n{value}\r\n').encode()
    body += f'--{boundary}--\r\n'.encode()
    started = api('POST', f'/api/v1/main/executions/{NAMESPACE}/{FLOW_ID}', body,
                  f'multipart/form-data; boundary={boundary}')
    execution_id = started['id']

    def finished():
        execution = api('GET', f'/api/v1/main/executions/{execution_id}')
        if execution['state']['current'] in {'SUCCESS', 'FAILED', 'KILLED',
                                              'WARNING', 'CANCELLED'}:
            return execution
        return None

    execution = eventually(finished, timeout=180)
    folder = ROOT / 'evidence/raw'
    folder.mkdir(exist_ok=True)
    (folder / f'{execution_id}.json').write_text(json.dumps(execution, indent=2))
    print(f"  execution={execution_id} state={execution['state']['current']}", flush=True)
    return execution


def task_output(execution, task_id):
    result = api('POST', f"/api/v1/main/executions/{execution['id']}/actions/eval",
                 ('{{ outputs.' + task_id + ' }}').encode(), 'text/plain')
    if result.get('error'):
        raise AssertionError(result['error'])
    output = json.loads(result['result'])
    path = ROOT / 'evidence/raw' / f"{execution['id']}-{task_id}.json"
    path.write_text(json.dumps(output, indent=2))
    return output


def bootstrap(sync_slots=True):
    compose('rm', '-s', '-f', 'publisher', 'subscriber', 'standby')
    for name in ['publisher', 'subscriber', 'standby']:
        result = subprocess.run(['docker', 'volume', 'rm', 'kestra-rehearsal_' + name],
                                capture_output=True, text=True)
        if result.returncode and 'no such volume' not in result.stderr.lower():
            raise RuntimeError(result.stderr)
    compose('up', '-d', '--wait', 'publisher', 'subscriber')
    compose('exec', '-T', 'publisher', 'sh', '/lab/replication-auth.sh')
    sql('publisher', 'SELECT pg_reload_conf();')
    table = 'CREATE TABLE rehearsal_items (id integer PRIMARY KEY, value text NOT NULL);'
    sql('publisher', table + '\nCREATE PUBLICATION rehearsal_pub FOR TABLE rehearsal_items;')
    sql('subscriber', table)
    sql('publisher', "SELECT pg_create_physical_replication_slot('lab_standby');")
    compose('up', '-d', '--wait', 'standby')
    if not sync_slots:
        sql('standby', "ALTER SYSTEM SET sync_replication_slots = off;")
        sql('standby', 'SELECT pg_reload_conf();')
    sql('publisher', "ALTER SYSTEM SET synchronized_standby_slots = 'lab_standby';")
    sql('publisher', 'SELECT pg_reload_conf();')
    password = ENV['LAB_DB_PASSWORD']
    compose('exec', '-T', '--user', 'postgres', 'subscriber', 'sh', '-c',
            'umask 077; cat > /var/lib/postgresql/.pgpass',
            data=f'*:*:rehearsal:lab:{password}\n')
    sql('subscriber', "CREATE SUBSCRIPTION rehearsal_sub CONNECTION "
        "'host=publisher port=5432 dbname=rehearsal user=lab "
        "passfile=/var/lib/postgresql/.pgpass' "
        "PUBLICATION rehearsal_pub WITH (failover=true, copy_data=false);")
    sql('publisher', "INSERT INTO rehearsal_items VALUES "
        "(1,'keep'),(2,'before'),(3,'remove');")
    eventually(lambda: sql('subscriber', 'SELECT count(*) FROM rehearsal_items;') == '3')
    if sync_slots:
        sql('publisher', 'SELECT pg_log_standby_snapshot();')
        eventually(lambda: sql('standby', "SELECT count(*) FROM pg_replication_slots "
                               "WHERE slot_name='rehearsal_sub' AND synced "
                               "AND NOT temporary AND invalidation_reason IS NULL;") == '1')
    return {
        'system_id': sql('publisher', 'SELECT system_identifier FROM pg_control_system();'),
        'subscriber_id': sql('subscriber', 'SELECT system_identifier FROM pg_control_system();'),
        'subscription_oid': sql('subscriber', "SELECT oid FROM pg_subscription "
                                "WHERE subname='rehearsal_sub';"),
        'origin_id': sql('subscriber', 'SELECT roident FROM pg_replication_origin;'),
    }


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['bootstrap']:
        print(json.dumps(bootstrap(), indent=2))
    elif sys.argv[1:] == ['install']:
        installed = install_flow()
        print(json.dumps({'flow': installed.get('id'), 'revision': installed.get('revision')}))
    else:
        raise SystemExit('Usage: python3 tests/lab_support.py bootstrap|install')
