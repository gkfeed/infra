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

The final status must show migrations `20260904184133` and `20260905082946`
with nothing pending. Then follow [offline dump transfer](offline-dump-transfer.md).

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

## Rehearsal overlay

`compose.rehearsal.yaml` replaces the production bind mount with a disposable
named volume and disables automatic restart. The transfer rehearsal uses two
separate PostgreSQL clusters because the application group roles are
cluster-wide and the role migration must run independently on both targets.

The rehearsal requires Bash, Docker Compose, GNU Make and coreutils, SQLite's
`sqlite3` CLI, `jq`, and the Python environment described in
[the importer README](../legacy-import/README.md).

Copy the two examples and set private local passwords:

```sh
cp .env.rehearsal-source.example .env.rehearsal-source
cp .env.rehearsal-restore.example .env.rehearsal-restore
chmod 0600 .env.rehearsal-source .env.rehearsal-restore
```

Run the complete rehearsal:

```sh
scripts/rehearse-dump-transfer.sh \
  /private/path/gkfeed.sqlite \
  /private/path/gkfeed-data.dump
```

The script imports into the source cluster, creates the dump, restores it into
the second migrated cluster, and compares every table and sequence. It stops
the source container and leaves the restored database running.

For local application checks, read the passwords from
`.env.rehearsal-restore` and use:

```dotenv
GKFEED_DATABASE_URL=postgres://gkfeed_api_login:<API_LOGIN_PASSWORD>@127.0.0.1:55435/gkfeed?sslmode=disable
DB_URL=postgresql://gkfeed_parser_login:<PARSER_LOGIN_PASSWORD>@127.0.0.1:55435/gkfeed?sslmode=disable
```

Do not remove the rehearsal volume until both applications pass their smoke
tests. The operator may stop the container without deleting data:

```sh
docker compose --project-name gkfeed-transfer-restore \
  --env-file .env.rehearsal-restore \
  -f compose.yaml -f compose.rehearsal.yaml stop postgres
```

Compose does not provide ongoing backups. Task I14 tracks backup scheduling,
retention, off-host storage, alerts, and periodic restore tests.
