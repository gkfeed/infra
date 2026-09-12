-- migrate:up

CREATE ROLE gkfeed_backup NOLOGIN;

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO gkfeed_backup', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO gkfeed_backup;
GRANT SELECT ON public.schema_migrations, public.users, public.feed,
    public.item, public.feed_parser, public.item_hash,
    public.webauthn_credentials, public.refresh_tokens
    TO gkfeed_backup;
GRANT SELECT ON SEQUENCE public.users_id_seq, public.feed_id_seq,
    public.item_id_seq, public.item_hash_id_seq
    TO gkfeed_backup;

-- migrate:down
