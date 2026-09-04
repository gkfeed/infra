# API contract

API revision: `58dd0be485a664179458d399fa8bd349459ea913`.

| Table | Columns | API access | Owner | Keys |
| --- | --- | --- | --- | --- |
| `users` | `id`, `name`, `hashed_password` | Read; update password hash | API | PK `id` |
| `feed` | `id`, `title`, `url`, `type`, `user_id` | Read, insert, delete | API | PK `id`; FK `user_id -> users.id` |
| `item` | `id`, `feed_id`, `title`, `text`, `date`, `link` | Read | Parser | PK `id`; FK `feed_id -> feed.id` |
| `deleted_items` | `user_id`, `item_id` | Read and insert | API | FKs to `users.id` and `item.id`; unique pair |
| `webauthn_credentials` | `id`, `user_id`, `credential`, `name`, `created_at`, `last_used_at` | Read, insert, update, delete | API | PK `id`; FK `user_id -> users.id` |
| `refresh_tokens` | `id`, `user_id`, `expires_at`, `created_at` | Read, insert, delete | API | PK `id`; FK `user_id -> users.id` |

`feed` and `item` are shared with the parser. Their IDs are `INTEGER`, text
columns are non-null, and timestamps are `TIMESTAMPTZ`.

## Open decisions

- Nullability and uniqueness for users and feeds.
- Delete cascades.
- Duplicate feed URL policy.
- Ownership checks for item tombstones.
- WebAuthn types: `BYTEA` plus `TEXT`, or `BYTEA` plus `JSONB`.
- Token schema: current `refresh_tokens` or legacy `auth_refresh_tokens`.
- Whether password conversion belongs in the importer.

SQLite `itemhash` and `auth_refresh_tokens` need owner approval before they can
become PostgreSQL tables.
