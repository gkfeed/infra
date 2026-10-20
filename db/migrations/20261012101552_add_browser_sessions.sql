-- migrate:up

CREATE TABLE public.browser_sessions (
    token_hash BYTEA PRIMARY KEY CHECK (octet_length(token_hash) = 32),
    user_id INTEGER NOT NULL REFERENCES public.users (id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (last_seen_at >= created_at),
    CHECK (expires_at > created_at)
);

CREATE INDEX browser_sessions_user_id_idx ON public.browser_sessions (user_id);
CREATE INDEX browser_sessions_expires_at_idx ON public.browser_sessions (expires_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.browser_sessions TO gkfeed_api;
GRANT SELECT ON public.browser_sessions TO gkfeed_backup;

-- migrate:down

