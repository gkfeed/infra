\set ON_ERROR_STOP on
BEGIN;

-- Run only on disposable PostgreSQL as the migration owner/superuser.
-- The helper runs with caller privileges and accepts only the named SQLSTATE.
CREATE FUNCTION pg_temp.expect_sqlstate(statement text, expected text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        IF SQLSTATE = expected THEN
            RETURN;
        END IF;
        RAISE;
    END;
    RAISE EXCEPTION 'Expected SQLSTATE %: %', expected, statement;
END
$$;

INSERT INTO public.users (name) VALUES ('browser-session-smoke');
INSERT INTO public.users (name) VALUES ('browser-session-other');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_roles WHERE rolname = 'gkfeed_api'
        AND NOT (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole
                 OR rolreplication OR rolbypassrls)
    ) OR has_schema_privilege('gkfeed_api', 'public', 'CREATE')
      OR has_database_privilege('gkfeed_api', current_database(), 'CREATE,TEMPORARY')
      OR EXISTS (
        SELECT FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
        WHERE c.oid = 'public.browser_sessions'::regclass
          AND r.rolname IN ('gkfeed_api', 'gkfeed_parser', 'gkfeed_backup')
      ) OR EXISTS (
        SELECT FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
        WHERE n.nspname = 'public' AND r.rolname = 'gkfeed_api'
      ) THEN
        RAISE EXCEPTION 'Unsafe API role attributes, DDL privileges or ownership';
    END IF;
    IF NOT has_table_privilege('gkfeed_api', 'public.browser_sessions', 'SELECT')
      OR NOT has_table_privilege('gkfeed_api', 'public.browser_sessions', 'INSERT')
      OR NOT has_table_privilege('gkfeed_api', 'public.browser_sessions', 'UPDATE')
      OR NOT has_table_privilege('gkfeed_api', 'public.browser_sessions', 'DELETE')
      OR has_table_privilege('gkfeed_api', 'public.browser_sessions', 'TRUNCATE,REFERENCES,TRIGGER')
      OR has_table_privilege('gkfeed_api', 'public.refresh_tokens', 'UPDATE') THEN
        RAISE EXCEPTION 'Incorrect browser session or refresh token privileges';
    END IF;
END
$$;

SET LOCAL ROLE gkfeed_api;
-- Match the API startup probe, creation, touch and logout query shapes.
SELECT token_hash, user_id, created_at, last_seen_at, expires_at
FROM public.browser_sessions LIMIT 0;

DO $$
DECLARE
    uid integer;
    other_uid integer;
    stamp timestamptz := CURRENT_TIMESTAMP;
    digest bytea := sha256('browser-session-smoke'::bytea);
    returned_uid integer;
    returned_expiry timestamptz;
    affected integer;
    column_name text;
    size integer;
BEGIN
    SELECT id INTO STRICT uid FROM public.users WHERE name = 'browser-session-smoke';
    SELECT id INTO STRICT other_uid FROM public.users WHERE name = 'browser-session-other';

    INSERT INTO public.browser_sessions
        (token_hash, user_id, created_at, last_seen_at, expires_at)
    VALUES (digest, uid, stamp, stamp, stamp + INTERVAL '90 days');
    IF NOT EXISTS (SELECT FROM public.browser_sessions
        WHERE token_hash = digest AND user_id = uid AND last_seen_at = stamp) THEN
        RAISE EXCEPTION 'Session creation/read failed';
    END IF;

    UPDATE public.browser_sessions
    SET last_seen_at = CASE WHEN last_seen_at < stamp + INTERVAL '1 day'
                           THEN stamp + INTERVAL '1 day' ELSE last_seen_at END
    WHERE token_hash = digest
      AND last_seen_at > stamp + INTERVAL '1 day' - INTERVAL '30 days'
      AND expires_at > stamp + INTERVAL '1 day'
    RETURNING user_id, expires_at INTO STRICT returned_uid, returned_expiry;
    IF returned_uid <> uid OR returned_expiry <> stamp + INTERVAL '90 days'
       OR NOT EXISTS (SELECT FROM public.browser_sessions
           WHERE token_hash = digest AND last_seen_at = stamp + INTERVAL '1 day') THEN
        RAISE EXCEPTION 'Touch failed or changed absolute expiry';
    END IF;
    PERFORM name FROM public.users WHERE id = returned_uid;

    -- An earlier request must not move activity backwards.
    UPDATE public.browser_sessions
    SET last_seen_at = CASE WHEN last_seen_at < stamp THEN stamp ELSE last_seen_at END
    WHERE token_hash = digest AND last_seen_at > stamp - INTERVAL '30 days'
      AND expires_at > stamp;
    IF NOT EXISTS (SELECT FROM public.browser_sessions
        WHERE token_hash = digest AND last_seen_at = stamp + INTERVAL '1 day') THEN
        RAISE EXCEPTION 'Touch moved activity backwards';
    END IF;

    FOREACH size IN ARRAY ARRAY[0, 31, 33] LOOP
        PERFORM pg_temp.expect_sqlstate(format(
            'UPDATE public.browser_sessions SET token_hash = decode(repeat(''ab'', %s), ''hex'')', size), '23514');
    END LOOP;
    FOREACH column_name IN ARRAY ARRAY[
        'token_hash', 'user_id', 'created_at', 'last_seen_at', 'expires_at'
    ] LOOP
        PERFORM pg_temp.expect_sqlstate(format(
            'UPDATE public.browser_sessions SET %I = NULL', column_name), '23502');
    END LOOP;
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE public.browser_sessions SET last_seen_at = created_at - INTERVAL ''1 microsecond''', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE public.browser_sessions SET expires_at = created_at', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE public.browser_sessions SET expires_at = created_at - INTERVAL ''1 microsecond''', '23514');
    PERFORM pg_temp.expect_sqlstate(format(
        'UPDATE public.browser_sessions SET user_id = %s',
        (SELECT max(id)::bigint + 1 FROM public.users)), '23503');
    PERFORM pg_temp.expect_sqlstate(
        'INSERT INTO public.browser_sessions SELECT * FROM public.browser_sessions', '23505');

    INSERT INTO public.browser_sessions VALUES
        (sha256('idle'::bytea), uid, stamp - INTERVAL '40 days',
         stamp - INTERVAL '30 days', stamp + INTERVAL '50 days'),
        (sha256('absolute'::bytea), uid, stamp - INTERVAL '90 days', stamp, stamp),
        (sha256('other'::bytea), other_uid, stamp, stamp, stamp + INTERVAL '90 days');
    UPDATE public.browser_sessions
    SET last_seen_at = CASE WHEN last_seen_at < stamp THEN stamp ELSE last_seen_at END
    WHERE token_hash IN (sha256('idle'::bytea), sha256('absolute'::bytea))
      AND last_seen_at > stamp - INTERVAL '30 days' AND expires_at > stamp;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 0 THEN
        RAISE EXCEPTION 'Expired session authenticated';
    END IF;

    DELETE FROM public.browser_sessions WHERE token_hash = digest;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 OR (SELECT count(*) FROM public.browser_sessions WHERE user_id = uid) <> 2 THEN
        RAISE EXCEPTION 'Current logout removed the wrong sessions';
    END IF;
    DELETE FROM public.browser_sessions WHERE token_hash = digest;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 0 THEN
        RAISE EXCEPTION 'Repeated logout was not idempotent';
    END IF;
    DELETE FROM public.browser_sessions WHERE user_id = uid;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 2 OR EXISTS (SELECT FROM public.browser_sessions WHERE user_id = uid)
       OR NOT EXISTS (SELECT FROM public.browser_sessions WHERE user_id = other_uid) THEN
        RAISE EXCEPTION 'Logout-all failed user isolation';
    END IF;
END
$$;

SELECT pg_temp.expect_sqlstate('CREATE TABLE public.browser_forbidden (id integer)', '42501');
SELECT pg_temp.expect_sqlstate('CREATE SCHEMA browser_forbidden', '42501');
SELECT pg_temp.expect_sqlstate('CREATE TEMP TABLE browser_forbidden (id integer)', '42501');
SELECT pg_temp.expect_sqlstate('ALTER TABLE public.browser_sessions ADD COLUMN forbidden integer', '42501');
SELECT pg_temp.expect_sqlstate('DROP TABLE public.browser_sessions', '42501');
SELECT pg_temp.expect_sqlstate('TRUNCATE public.browser_sessions', '42501');
SELECT pg_temp.expect_sqlstate('UPDATE public.refresh_tokens SET expires_at = now()', '42501');
RESET ROLE;

-- Test ON DELETE RESTRICT as an operator: the API cannot delete users at all.
SELECT pg_temp.expect_sqlstate(
    'DELETE FROM public.users WHERE name = ''browser-session-other''', '23503');
DELETE FROM public.browser_sessions
WHERE user_id = (SELECT id FROM public.users WHERE name = 'browser-session-other');
DELETE FROM public.users WHERE name = 'browser-session-other';

SET LOCAL ROLE gkfeed_parser;
SELECT pg_temp.expect_sqlstate('SELECT * FROM public.browser_sessions', '42501');
SELECT pg_temp.expect_sqlstate('INSERT INTO public.browser_sessions DEFAULT VALUES', '42501');
SELECT pg_temp.expect_sqlstate('UPDATE public.browser_sessions SET last_seen_at = now()', '42501');
SELECT pg_temp.expect_sqlstate('DELETE FROM public.browser_sessions', '42501');

ROLLBACK;
\echo Browser session smoke checks passed.
