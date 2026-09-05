-- migrate:up

CREATE ROLE gkfeed_parser NOLOGIN;
CREATE ROLE gkfeed_api NOLOGIN;

-- PUBLIC grants are inherited by every role, even a new NOLOGIN group.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
DO $$
BEGIN
    EXECUTE format('REVOKE CREATE, TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO gkfeed_parser, gkfeed_api;
GRANT SELECT ON public.schema_migrations TO gkfeed_parser, gkfeed_api;

GRANT SELECT ON public.feed, public.item, public.feed_parser, public.item_hash
    TO gkfeed_parser;
GRANT INSERT ON public.item, public.feed_parser, public.item_hash TO gkfeed_parser;
GRANT UPDATE (valid_for) ON public.feed_parser TO gkfeed_parser;
GRANT UPDATE (feed_id) ON public.item_hash TO gkfeed_parser;
GRANT USAGE ON SEQUENCE public.item_id_seq, public.item_hash_id_seq TO gkfeed_parser;

GRANT SELECT ON public.users, public.feed, public.item,
    public.webauthn_credentials, public.refresh_tokens TO gkfeed_api;
GRANT UPDATE (hashed_password) ON public.users TO gkfeed_api;
GRANT INSERT, DELETE ON public.feed, public.webauthn_credentials,
    public.refresh_tokens TO gkfeed_api;
GRANT UPDATE ON public.webauthn_credentials TO gkfeed_api;
GRANT DELETE ON public.item TO gkfeed_api;
GRANT USAGE ON SEQUENCE public.feed_id_seq TO gkfeed_api;

-- migrate:down
