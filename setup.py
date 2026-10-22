import base64
import os
from pathlib import Path
import secrets


path = Path(__file__).resolve().parent / '.env'
if path.exists():
    print('Using existing private lab configuration.')
else:
    database_password = secrets.token_urlsafe(24)
    admin_password = 'LabA1' + secrets.token_urlsafe(24)
    encoded = base64.b64encode(database_password.encode()).decode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(f'LAB_DB_PASSWORD={database_password}\n'
                     f'SECRET_LAB_DB_PASSWORD={encoded}\n'
                     f'LAB_ADMIN_PASSWORD={admin_password}\n')
    print('Created private lab configuration; no credentials were printed.')
