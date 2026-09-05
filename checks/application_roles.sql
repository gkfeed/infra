\set ON_ERROR_STOP on
BEGIN;

-- Run only on a disposable database as its migration owner/superuser.
-- Rolled-back inserts still advance identity sequences.
CREATE TEMP TABLE privilege_check_init (id integer);
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

INSERT INTO public.users (name) VALUES ('i05-smoke') RETURNING id AS user_id \gset

SET LOCAL ROLE gkfeed_api;
SELECT * FROM public.schema_migrations;
SELECT * FROM public.users WHERE id = :user_id;
UPDATE public.users SET hashed_password = NULL WHERE id = :user_id;
INSERT INTO public.feed (title, url, type, user_id)
VALUES ('smoke', 'https://example.invalid/i05', 'rss', :user_id)
RETURNING id AS feed_id \gset
INSERT INTO public.webauthn_credentials (id, user_id, credential)
VALUES ('\x0105', :user_id, '{}');
SELECT * FROM public.webauthn_credentials WHERE id = '\x0105';
UPDATE public.webauthn_credentials SET name = 'smoke', last_used_at = now()
WHERE id = '\x0105';
DELETE FROM public.webauthn_credentials WHERE id = '\x0105';
INSERT INTO public.refresh_tokens (id, user_id, expires_at)
VALUES ('i05-smoke', :user_id, now());
SELECT * FROM public.refresh_tokens WHERE id = 'i05-smoke';
DELETE FROM public.refresh_tokens WHERE id = 'i05-smoke';

SET LOCAL ROLE gkfeed_parser;
SELECT * FROM public.schema_migrations;
SELECT * FROM public.feed WHERE id = :feed_id;
INSERT INTO public.item (feed_id, title, text, date, link)
VALUES (:feed_id, 'smoke', '', now(), '') RETURNING id AS item_id \gset
SELECT * FROM public.item WHERE id = :item_id;
-- Leave another item for the feed cascade check.
INSERT INTO public.item (feed_id, title, text, date, link)
VALUES (:feed_id, 'smoke', '', now(), '');
INSERT INTO public.feed_parser (feed_id, valid_for) VALUES (:feed_id, now());
INSERT INTO public.feed_parser (feed_id, valid_for) VALUES (:feed_id, now())
ON CONFLICT (feed_id) DO UPDATE SET valid_for = excluded.valid_for;
SELECT * FROM public.feed_parser WHERE feed_id = :feed_id;
INSERT INTO public.item_hash (hash) VALUES ('i05-smoke') RETURNING id AS hash_id \gset
UPDATE public.item_hash SET feed_id = :feed_id WHERE id = :hash_id;
SELECT * FROM public.item_hash WHERE id = :hash_id;

SELECT pg_temp.expect_denied('DELETE FROM public.item');
SELECT pg_temp.expect_denied('UPDATE public.item SET title = title');
SELECT pg_temp.expect_denied('INSERT INTO public.feed DEFAULT VALUES');
SELECT pg_temp.expect_denied('UPDATE public.feed SET title = title');
SELECT pg_temp.expect_denied('DELETE FROM public.feed');
SELECT pg_temp.expect_denied('DELETE FROM public.feed_parser');
SELECT pg_temp.expect_denied('UPDATE public.feed_parser SET feed_id = feed_id');
SELECT pg_temp.expect_denied('DELETE FROM public.item_hash');
SELECT pg_temp.expect_denied('UPDATE public.item_hash SET hash = hash');
SELECT pg_temp.expect_denied('SELECT * FROM public.users');
SELECT pg_temp.expect_denied('SELECT * FROM public.webauthn_credentials');
SELECT pg_temp.expect_denied('SELECT * FROM public.refresh_tokens');
SELECT pg_temp.expect_denied('SELECT nextval(''public.feed_id_seq'')');
SELECT pg_temp.expect_denied('SELECT setval(''public.item_id_seq'', 1)');

SET LOCAL ROLE gkfeed_api;
DELETE FROM public.item WHERE id = :item_id RETURNING id;
-- Feed deletion must also remove parser-owned rows without direct grants.
DELETE FROM public.feed WHERE id = :feed_id RETURNING id;
SELECT pg_temp.expect_denied('INSERT INTO public.item DEFAULT VALUES');
SELECT pg_temp.expect_denied('UPDATE public.item SET title = title');
SELECT pg_temp.expect_denied('UPDATE public.feed SET title = title');
SELECT pg_temp.expect_denied('INSERT INTO public.users DEFAULT VALUES');
SELECT pg_temp.expect_denied('DELETE FROM public.users');
SELECT pg_temp.expect_denied('UPDATE public.users SET name = name');
SELECT pg_temp.expect_denied('UPDATE public.refresh_tokens SET expires_at = now()');
SELECT pg_temp.expect_denied('SELECT * FROM public.feed_parser');
SELECT pg_temp.expect_denied('SELECT * FROM public.item_hash');
SELECT pg_temp.expect_denied('SELECT nextval(''public.item_id_seq'')');
SELECT pg_temp.expect_denied('SELECT nextval(''public.users_id_seq'')');
SELECT pg_temp.expect_denied('SELECT setval(''public.feed_id_seq'', 1)');

RESET ROLE;
DO $$
DECLARE
    application_role text;
    table_name text;
BEGIN
    FOREACH application_role IN ARRAY ARRAY['gkfeed_parser', 'gkfeed_api'] LOOP
        IF EXISTS (
            SELECT FROM pg_roles WHERE rolname = application_role
            AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
        ) THEN
            RAISE EXCEPTION 'Unexpected role attributes for %', application_role;
        END IF;
        EXECUTE format('SET LOCAL ROLE %I', application_role);
        PERFORM pg_temp.expect_denied('CREATE TABLE public.i05_forbidden (id integer)');
        PERFORM pg_temp.expect_denied('CREATE SCHEMA i05_forbidden');
        PERFORM pg_temp.expect_denied('CREATE TEMP TABLE i05_forbidden (id integer)');
        PERFORM pg_temp.expect_denied('INSERT INTO public.schema_migrations VALUES (''00000000000000'')');
        PERFORM pg_temp.expect_denied('UPDATE public.schema_migrations SET version = version');
        PERFORM pg_temp.expect_denied('DELETE FROM public.schema_migrations');
        FOREACH table_name IN ARRAY ARRAY['users', 'feed', 'item', 'feed_parser',
            'item_hash', 'webauthn_credentials', 'refresh_tokens', 'schema_migrations'] LOOP
            PERFORM pg_temp.expect_denied(format('ALTER TABLE public.%I ADD COLUMN forbidden integer', table_name));
            PERFORM pg_temp.expect_denied(format('DROP TABLE public.%I CASCADE', table_name));
            PERFORM pg_temp.expect_denied(format('TRUNCATE public.%I CASCADE', table_name));
        END LOOP;
        RESET ROLE;
    END LOOP;
    IF EXISTS (SELECT FROM public.item WHERE title = 'smoke')
        OR EXISTS (SELECT FROM public.feed_parser)
        OR EXISTS (SELECT FROM public.item_hash WHERE hash = 'i05-smoke') THEN
        RAISE EXCEPTION 'API deletion left dependent rows';
    END IF;
END
$$;
ROLLBACK;
\echo Application role smoke checks passed.
