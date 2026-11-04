-- migrate:up

CREATE INDEX item_feed_id_idx ON public.item (feed_id);

-- migrate:down
