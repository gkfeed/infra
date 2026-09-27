"""Check per-user change ordering on a disposable migrated PostgreSQL database.

Requires psycopg 3. Run with DATABASE_URL set to the disposable database.
"""

import os
import threading
import time
import uuid

import psycopg


dsn = os.environ["DATABASE_URL"]
name = "changes-concurrency-" + uuid.uuid4().hex
started = threading.Event()
finished = threading.Event()
worker_error = []
worker_pid = []

with psycopg.connect(dsn) as setup:
    user_id = setup.execute(
        "INSERT INTO public.users (name) VALUES (%s) RETURNING id", (name,)
    ).fetchone()[0]
    feed_id = setup.execute(
        "INSERT INTO public.feed (title, url, type, user_id) "
        "VALUES (%s, %s, 'rss', %s) RETURNING id",
        (name, "https://example.invalid/" + name, user_id),
    ).fetchone()[0]


def insert_second():
    try:
        with psycopg.connect(dsn) as connection:
            worker_pid.append(connection.execute("SELECT pg_backend_pid()").fetchone()[0])
            started.set()
            connection.execute(
                "INSERT INTO public.item (feed_id, title, text, date, link) "
                "VALUES (%s, 'second', '', now(), '')",
                (feed_id,),
            )
    except Exception as error:
        worker_error.append(error)
    finally:
        finished.set()


try:
    with psycopg.connect(dsn) as first, psycopg.connect(dsn) as observer:
        first.execute(
            "INSERT INTO public.item (feed_id, title, text, date, link) "
            "VALUES (%s, 'first', '', now(), '')",
            (feed_id,),
        )
        thread = threading.Thread(target=insert_second)
        thread.start()
        assert started.wait(5), "Second transaction did not start"

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            waiting = observer.execute(
                "SELECT wait_event_type = 'Lock' AND wait_event = 'advisory' "
                "FROM pg_stat_activity WHERE pid = %s",
                (worker_pid[0],),
            ).fetchone()
            if waiting and waiting[0]:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("Second transaction did not wait for the user lock")

        assert not finished.is_set(), "Second transaction finished before the first"
        assert observer.execute(
            "SELECT count(*) FROM public.item_changes WHERE user_id = %s", (user_id,)
        ).fetchone()[0] == 0, "Uncommitted change became visible"

        first.commit()
        thread.join(timeout=5)
        assert finished.is_set(), "Second transaction stayed blocked after commit"
        assert not worker_error, worker_error
        rows = observer.execute(
            "SELECT id, payload->>'Title' FROM public.item_changes "
            "WHERE user_id = %s ORDER BY id", (user_id,)
        ).fetchall()
        assert len(rows) == 2 and rows[0][1] == "first" and rows[1][1] == "second"
        assert rows[0][0] < rows[1][0], rows
        print("Item change concurrency check passed.")
finally:
    with psycopg.connect(dsn) as cleanup:
        cleanup.execute("DELETE FROM public.feed WHERE id = %s", (feed_id,))
        cleanup.execute("DELETE FROM public.item_changes WHERE user_id = %s", (user_id,))
        cleanup.execute("DELETE FROM public.users WHERE id = %s", (user_id,))
