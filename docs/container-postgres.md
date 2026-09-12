# PostgreSQL container

`compose.yaml` runs the production PostgreSQL 17 database. It binds PostgreSQL
to loopback only. API and parser processes on the same host connect through
`127.0.0.1`; remote clients need an SSH tunnel.

The Compose file does not create application LOGIN roles or run migrations.
The designated operator performs both actions from this repository.

## Prepare the host

Create the persistent data directory on the production server:

```sh
sudo install -d -m 0700 /srv/gkfeed/postgres/17/data
cp .env.example .env
chmod 0600 .env
```

Set a long random `POSTGRES_PASSWORD` in `.env`. Put the same percent-encoded
password in `DATABASE_URL`. Keep `.env` off Git and out of shell history.

The default bind mount is `/srv/gkfeed/postgres/17/data`. Set
`POSTGRES_DATA_DIR` in `.env` if the server uses another persistent disk. The
official image starts as root, assigns the mounted directory to its internal
`postgres` account, then drops privileges. Check the resulting owner after the
first start. Do not hard-code a host UID before checking the selected image.

Start the database and inspect its health:

```sh
docker compose config --quiet
docker compose up -d --wait postgres
docker compose ps
```

Apply migrations before restoring data:

```sh
make status
make migrate
make status
```

The final status must show no pending migrations.

## Application logins

Create LOGIN identities after migrations. Run `psql "$DATABASE_URL"`, then use
`\password` so passwords do not enter shell history:

```sql
CREATE ROLE gkfeed_api_login LOGIN INHERIT NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS IN ROLE gkfeed_api;
\password gkfeed_api_login
CREATE ROLE gkfeed_parser_login LOGIN INHERIT NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS IN ROLE gkfeed_parser;
\password gkfeed_parser_login
```

Use `GKFEED_DATABASE_URL` for API and `DB_URL` for parser. Each URL must name
its LOGIN role, not `gkfeed_owner`.

Compose does not schedule backups. The Russian
[PostgreSQL backup runbook](postgres-backups.ru.md) documents the hourly
Telegram backup, private retry spool, alerts, and manual restore procedure.
