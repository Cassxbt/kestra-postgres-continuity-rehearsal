#!/bin/sh
set -eu
printf '\nhost replication lab all scram-sha-256\n' >> "$PGDATA/pg_hba.conf"
