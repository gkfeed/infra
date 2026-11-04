\set ON_ERROR_STOP on
BEGIN;

-- Run on a disposable migrated database. Fixture rows roll back; identity IDs do not.
CREATE FUNCTION pg_temp.assert_true(ok boolean, message text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT COALESCE(ok, false) THEN
        RAISE EXCEPTION '%', message;
    END IF;
END
$$;

SELECT pg_temp.assert_true(
    (SELECT i.indisvalid AND i.indisready AND NOT i.indisunique
            AND i.indnkeyatts = 1 AND i.indnatts = 1
            AND i.indpred IS NULL AND i.indexprs IS NULL
            AND am.amname = 'btree' AND a.attname = 'feed_id'
     FROM pg_index i
     JOIN pg_class idx ON idx.oid = i.indexrelid
     JOIN pg_am am ON am.oid = idx.relam
     JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
     WHERE i.indexrelid = 'public.item_feed_id_idx'::regclass
       AND i.indrelid = 'public.item'::regclass),
    'Expected a valid non-unique item(feed_id) B-tree index');

INSERT INTO public.users (name) VALUES ('item-feed-index-check');
INSERT INTO public.feed (title, url, type, user_id)
SELECT title, 'https://example.invalid/' || title, 'rss', id
FROM public.users CROSS JOIN (VALUES ('index-feed-a'), ('index-feed-b')) f(title)
WHERE name = 'item-feed-index-check';

SET LOCAL ROLE gkfeed_parser;
-- Long, non-compressible-looking text exceeds the B-tree index tuple limit if
-- included as a key. Duplicate identities and date changes remain allowed.
INSERT INTO public.item (feed_id, title, link, text, date)
SELECT f.id, 'same', 'https://example.invalid/item',
       (SELECT string_agg(md5(n::text), '') FROM generate_series(1, 200) n), d
FROM public.feed f CROSS JOIN (VALUES ('2026-01-01'::timestamptz),
                                     ('2026-01-02'::timestamptz)) dates(d)
WHERE f.title IN ('index-feed-a', 'index-feed-b');

SELECT pg_temp.assert_true(
    (SELECT count(*) = 2 FROM public.item i
     WHERE i.feed_id = (SELECT id FROM public.feed WHERE title = 'index-feed-a')
       AND (i.title, i.link, i.text) IN
           (VALUES ('same', 'https://example.invalid/item',
                    (SELECT string_agg(md5(n::text), '') FROM generate_series(1, 200) n)),
                   ('missing', 'https://example.invalid/item', 'missing'))),
    'Fallback identity must be scoped by feed and exclude date');
SELECT pg_temp.assert_true(
    (SELECT count(*) = 0 FROM public.item i
     WHERE i.feed_id = (SELECT id FROM public.feed WHERE title = 'index-feed-a')
       AND (i.title, i.link, i.text) IN (VALUES ('same', 'https://example.invalid/item', 'different'))),
    'Different text must not match');
RESET ROLE;

SET LOCAL ROLE gkfeed_api;
DELETE FROM public.feed WHERE title = 'index-feed-a';
SELECT pg_temp.assert_true(
    (SELECT count(*) = 2 FROM public.item WHERE title = 'same'),
    'Feed cascade must remove only the deleted feed items');
RESET ROLE;
ROLLBACK;
\echo Item feed index checks passed.
