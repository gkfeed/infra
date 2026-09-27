-- migrate:up

CREATE TABLE public.item_changes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    payload JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX item_changes_user_id_id_idx ON public.item_changes (user_id, id);
GRANT SELECT ON public.item_changes TO gkfeed_api, gkfeed_backup;
GRANT SELECT ON SEQUENCE public.item_changes_id_seq TO gkfeed_backup;

CREATE FUNCTION public.record_item_change() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    old_user INTEGER;
    new_user INTEGER;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        SELECT user_id INTO old_user FROM public.feed WHERE id = OLD.feed_id;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        SELECT user_id INTO new_user FROM public.feed WHERE id = NEW.feed_id;
    END IF;

    -- Hold the per-user lock until commit before allocating a change ID.
    -- A later transaction must not publish a higher ID first.
    IF old_user IS NOT NULL AND new_user IS NOT NULL AND old_user <> new_user THEN
        PERFORM pg_advisory_xact_lock(193648, LEAST(old_user, new_user));
        PERFORM pg_advisory_xact_lock(193648, GREATEST(old_user, new_user));
    ELSIF COALESCE(old_user, new_user) IS NOT NULL THEN
        PERFORM pg_advisory_xact_lock(193648, COALESCE(old_user, new_user));
    END IF;

    IF old_user IS NOT NULL AND
       (TG_OP = 'DELETE' OR old_user IS DISTINCT FROM new_user) THEN
        INSERT INTO public.item_changes (user_id, item_id)
        VALUES (old_user, OLD.id);
    END IF;
    IF new_user IS NOT NULL THEN
        INSERT INTO public.item_changes (user_id, item_id, payload)
        VALUES (new_user, NEW.id, jsonb_build_object(
            'ID', NEW.id, 'FeedID', NEW.feed_id, 'Title', NEW.title,
            'Text', NEW.text, 'Date', NEW.date, 'Link', NEW.link));
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER item_change_after_write
AFTER INSERT OR UPDATE OR DELETE ON public.item
FOR EACH ROW EXECUTE FUNCTION public.record_item_change();

-- Record tombstones while the feed row still exists. The later FK cascade
-- deletes its items after the feed is gone, so their item trigger cannot
-- resolve the user and will not write duplicate tombstones.
CREATE FUNCTION public.record_feed_item_deletions() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(193648, OLD.user_id);
    INSERT INTO public.item_changes (user_id, item_id)
    SELECT OLD.user_id, id FROM public.item WHERE feed_id = OLD.id ORDER BY id;
    RETURN OLD;
END;
$$;

CREATE TRIGGER feed_items_before_delete
BEFORE DELETE ON public.feed
FOR EACH ROW EXECUTE FUNCTION public.record_feed_item_deletions();

REVOKE ALL ON FUNCTION public.record_item_change() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.record_feed_item_deletions() FROM PUBLIC;

-- migrate:down
