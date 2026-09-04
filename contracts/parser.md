# Parser contract

Parser revision: `0ff1d15ab0317574635dc7062b231a524b4f4cd5`.

| Table | Columns | Parser access | Owner | Keys |
| --- | --- | --- | --- | --- |
| `feed` | `id INTEGER`, `title TEXT`, `url TEXT`, `type TEXT` | Read | API | PK `id` |
| `item` | `id INTEGER`, `feed_id INTEGER`, `title TEXT`, `text TEXT`, `date TIMESTAMPTZ`, `link TEXT` | Read and insert | Parser | PK `id`; FK `feed_id -> feed.id` |
| `feed_parser` | `feed_id INTEGER`, `valid_for TIMESTAMPTZ` | Read and upsert | Parser | PK/FK `feed_id -> feed.id ON DELETE CASCADE` |
| `item_hash` | `id INTEGER`, `hash TEXT`, nullable `feed_id INTEGER` | Read, insert, and assign legacy hashes to a feed | Parser | PK `id`; FK `feed_id -> feed.id ON DELETE CASCADE`; unique `(feed_id, hash)` |

All columns are non-null except legacy `item_hash.feed_id`. New hashes include
a feed ID. The parser only reads `feed`; test helpers account for its feed
writes.

SQLite `itemhash` is import data, not a PostgreSQL table.

