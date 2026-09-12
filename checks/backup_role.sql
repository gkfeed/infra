\set ON_ERROR_STOP on
BEGIN;

-- Run only on a disposable database as its migration owner/superuser.
CREATE FUNCTION pg_temp.expect_denied(statement text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN insufficient_privilege THEN
        RETURN;
    END;
    RAISE EXCEPTION 'Expected insufficient_privilege: %', statement;
END
$$;

DO $$
DECLARE
    table_name text;
    sequence_name text;
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_roles
        WHERE rolname = 'gkfeed_backup'
          AND NOT rolcanlogin
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolreplication
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'gkfeed_backup is missing or has unsafe attributes';
    END IF;

    IF NOT has_database_privilege('gkfeed_backup', current_database(), 'CONNECT')
       OR NOT has_schema_privilege('gkfeed_backup', 'public', 'USAGE')
       OR has_schema_privilege('gkfeed_backup', 'public', 'CREATE')
       OR has_database_privilege('gkfeed_backup', current_database(), 'TEMPORARY') THEN
        RAISE EXCEPTION 'gkfeed_backup database or schema privileges are incorrect';
    END IF;

    FOREACH table_name IN ARRAY ARRAY[
        'schema_migrations', 'users', 'feed', 'item', 'feed_parser',
        'item_hash', 'webauthn_credentials', 'refresh_tokens'
    ] LOOP
        IF NOT has_table_privilege('gkfeed_backup', 'public.' || table_name, 'SELECT')
           OR has_table_privilege(
               'gkfeed_backup', 'public.' || table_name,
               'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
           ) THEN
            RAISE EXCEPTION 'gkfeed_backup table privileges are incorrect for %', table_name;
        END IF;
    END LOOP;

    FOREACH sequence_name IN ARRAY ARRAY[
        'users_id_seq', 'feed_id_seq', 'item_id_seq', 'item_hash_id_seq'
    ] LOOP
        IF NOT has_sequence_privilege(
                'gkfeed_backup', 'public.' || sequence_name, 'SELECT'
            )
           OR has_sequence_privilege(
                'gkfeed_backup', 'public.' || sequence_name, 'USAGE, UPDATE'
            ) THEN
            RAISE EXCEPTION 'gkfeed_backup sequence privileges are incorrect for %',
                sequence_name;
        END IF;
    END LOOP;
END
$$;

SET LOCAL ROLE gkfeed_backup;
SELECT * FROM public.schema_migrations;
SELECT * FROM public.users;
SELECT * FROM public.feed;
SELECT * FROM public.item;
SELECT * FROM public.feed_parser;
SELECT * FROM public.item_hash;
SELECT * FROM public.webauthn_credentials;
SELECT * FROM public.refresh_tokens;
SELECT last_value FROM public.users_id_seq;
SELECT last_value FROM public.feed_id_seq;
SELECT last_value FROM public.item_id_seq;
SELECT last_value FROM public.item_hash_id_seq;

SELECT pg_temp.expect_denied('INSERT INTO public.users (name) VALUES (''forbidden'')');
SELECT pg_temp.expect_denied('UPDATE public.feed SET title = title');
SELECT pg_temp.expect_denied('DELETE FROM public.item');
SELECT pg_temp.expect_denied('TRUNCATE public.item_hash');
SELECT pg_temp.expect_denied('SELECT nextval(''public.item_id_seq'')');
SELECT pg_temp.expect_denied('SELECT setval(''public.item_id_seq'', 1)');
SELECT pg_temp.expect_denied('CREATE TABLE public.backup_forbidden (id integer)');
SELECT pg_temp.expect_denied('CREATE SCHEMA backup_forbidden');
SELECT pg_temp.expect_denied('CREATE TEMP TABLE backup_forbidden (id integer)');

ROLLBACK;
\echo Backup role smoke checks passed.
