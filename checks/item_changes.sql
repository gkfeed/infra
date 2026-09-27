\set ON_ERROR_STOP on
BEGIN;

-- Run against a disposable database. Fixture rows roll back; identity IDs do not.
CREATE FUNCTION pg_temp.assert_true(ok boolean, message text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT COALESCE(ok, false) THEN
        RAISE EXCEPTION '%', message;
    END IF;
END
$$;

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

INSERT INTO public.users (name) VALUES ('changes-check-one'), ('changes-check-two');
INSERT INTO public.feed (title, url, type, user_id)
SELECT 'one', 'https://example.invalid/changes-one', 'rss', id
FROM public.users WHERE name = 'changes-check-one';
INSERT INTO public.feed (title, url, type, user_id)
SELECT 'two', 'https://example.invalid/changes-two', 'rss', id
FROM public.users WHERE name = 'changes-check-two';

SET LOCAL ROLE gkfeed_parser;
INSERT INTO public.item (feed_id, title, text, date, link)
SELECT id, 'first', 'body', '2026-09-27 12:00:00+00', 'https://example.invalid/first'
FROM public.feed WHERE title = 'one';
INSERT INTO public.item (feed_id, title, text, date, link)
SELECT id, 'second', 'body', '2026-09-27 12:00:00+00', 'https://example.invalid/second'
FROM public.feed WHERE title = 'one';
SELECT pg_temp.expect_denied('SELECT * FROM public.item_changes');
SELECT pg_temp.expect_denied('INSERT INTO public.item_changes (user_id, item_id) VALUES (1, 1)');
RESET ROLE;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 2 AND bool_and(payload IS NOT NULL)
     FROM public.item_changes), 'Parser inserts were not recorded');
SELECT pg_temp.assert_true(
    (SELECT bool_and(payload->>'Title' = item.title AND
                     (payload->>'ID')::integer = item.id AND
                     (payload->>'FeedID')::integer = item.feed_id AND
                     payload->>'Text' = item.text AND
                     payload->>'Link' = item.link AND
                     (payload->>'Date')::timestamptz = item.date)
     FROM public.item_changes JOIN public.item ON item.id = item_changes.item_id),
    'Insert payload differs from item');

UPDATE public.item SET title = 'updated' WHERE title = 'first';
SELECT pg_temp.assert_true(
    (SELECT count(*) = 1 FROM public.item_changes WHERE payload->>'Title' = 'updated'),
    'Update was not recorded');

SET LOCAL ROLE gkfeed_api;
SELECT pg_temp.assert_true(
    (SELECT count(*) = 3 FROM public.item_changes), 'API cannot read changes');
SELECT pg_temp.expect_denied('INSERT INTO public.item_changes (user_id, item_id) VALUES (1, 1)');
SELECT pg_temp.expect_denied('DELETE FROM public.item_changes');
SELECT pg_temp.expect_denied('SELECT nextval(''public.item_changes_id_seq'')');
DELETE FROM public.item WHERE title = 'updated';
RESET ROLE;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 1 FROM public.item_changes WHERE payload IS NULL),
    'Direct item delete did not write one tombstone');

SET LOCAL ROLE gkfeed_api;
DELETE FROM public.feed WHERE title = 'one';
RESET ROLE;

SELECT pg_temp.assert_true(
    (SELECT count(*) = 2 FROM public.item_changes WHERE payload IS NULL),
    'Feed cascade did not write exactly one more tombstone');
SELECT pg_temp.assert_true(
    (SELECT count(*) = 0 FROM public.item), 'Feed cascade left an item');

INSERT INTO public.item (feed_id, title, text, date, link)
SELECT id, 'other-user', '', now(), '' FROM public.feed WHERE title = 'two';
SELECT pg_temp.assert_true(
    (SELECT count(DISTINCT user_id) = 2 FROM public.item_changes),
    'Changes did not preserve user identity');
SELECT pg_temp.assert_true(
    (SELECT count(*) = 1 FROM public.item_changes
     WHERE user_id = (SELECT user_id FROM public.feed WHERE title = 'two')),
    'Other user sees unexpected changes');

SET LOCAL ROLE gkfeed_backup;
SELECT pg_temp.assert_true(
    (SELECT count(*) = 6 FROM public.item_changes), 'Backup cannot read changes');
SELECT pg_temp.expect_denied('DELETE FROM public.item_changes');
RESET ROLE;

SELECT pg_temp.assert_true(
    (SELECT NOT rolcanlogin FROM pg_roles WHERE rolname = 'gkfeed_api') AND
    (SELECT NOT rolcanlogin FROM pg_roles WHERE rolname = 'gkfeed_parser'),
    'Application group role has LOGIN');

ROLLBACK;
\echo Item change checks passed.
