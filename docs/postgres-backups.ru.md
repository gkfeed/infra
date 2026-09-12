# Резервное копирование PostgreSQL в Telegram

Скрипт `scripts/backup-postgres-telegram.sh` каждый час создаёт полный logical
dump базы PostgreSQL 17 в custom format. Он проверяет архив через
`pg_restore --list`, считает SHA-256 и отправляет данные в Telegram. Manifest
уходит последним и отмечает полный набор как готовый к восстановлению.

Текущие параметры процесса:

- RPO не более одного часа;
- целевой RTO не более четырёх часов;
- запуск через cron в пятую минуту каждого часа;
- Telegram является единственным off-host хранилищем;
- сообщения в Telegram автоматически не удаляются;
- регулярная проверка восстановления не запускается.

Bot API не использует end-to-end encryption. Архив содержит пользователей,
refresh tokens, WebAuthn credentials и остальные данные базы и отправляется без
дополнительного шифрования. Это принятое ограничение этой схемы.

## Роль PostgreSQL

Миграция `20260911093048_add_backup_role.sql` создаёт группу
`gkfeed_backup NOLOGIN`. Она может подключаться к базе и читать все текущие
таблицы и sequences, но не может менять данные или выполнять DDL.

После merge оператор применяет миграцию обычным способом из этого репозитория.
Затем он создаёт LOGIN identity вне Git. Пароль безопаснее задать интерактивной
командой `\password`, чтобы он не попал в shell history или список процессов:

```sh
psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1
```

```sql
CREATE ROLE gkfeed_backup_login LOGIN IN ROLE gkfeed_backup;
\password gkfeed_backup_login
```

LOGIN identity не должна владеть объектами, иметь дополнительные memberships
или атрибуты `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION` и
`BYPASSRLS`. При добавлении таблицы или sequence новая миграция должна выдать
нужный `SELECT` роли `gkfeed_backup`.

## Настройка сервера

Создайте закрытые каталоги от имени оператора, запускающего cron:

```sh
sudo install -d -o ubuntu -g ubuntu -m 0700 /srv/gkfeed/backups
install -d -m 0700 /home/ubuntu/.config/gkfeed /home/ubuntu/.local/state
```

Скопируйте `.env.backup.example` вне Git и заполните значения:

```sh
install -m 0600 .env.backup.example /home/ubuntu/.config/gkfeed/backup.env
```

Файл содержит отдельный PostgreSQL URL, Telegram bot token и chat ID. Скрипт
откажется читать файл с mode, отличным от `0400` или `0600`.

Проверьте один ручной запуск:

```sh
scripts/backup-postgres-telegram.sh /home/ubuntu/.config/gkfeed/backup.env
```

После проверки добавьте строку через `crontab -e` пользователя `ubuntu`:

```cron
5 * * * * /usr/bin/flock -n /home/ubuntu/.local/state/gkfeed-postgres-backup.lock /home/ubuntu/github/gkfeed/infra/scripts/backup-postgres-telegram.sh /home/ubuntu/.config/gkfeed/backup.env
```

Все запуски используют образ `postgres:17.10-bookworm`, закреплённый в
репозитории. Скрипт пишет результат в stderr и syslog с тегом
`gkfeed-postgres-backup`.

## Отправка и очередь ошибок

Файл размером до `BACKUP_PART_BYTES` отправляется одним документом. Больший
архив делится на части. Значение по умолчанию равно 45 000 000 байт и оставляет
запас до [лимита Bot API в 50 MB](https://core.telegram.org/bots/api#senddocument).

Manifest содержит имя исходного dump, его размер и SHA-256, а также размер и
SHA-256 каждой части. При частичном сбое `.sent-*` markers позволяют следующему
запуску продолжить с первой неподтверждённой части. После отправки всех частей
скрипт отправляет manifest. Только после успешного ответа Telegram локальный
каталог этого backup удаляется.

Непереданные наборы остаются в `BACKUP_SPOOL_DIR/pending` и повторно
отправляются каждый час. Скрипт не удаляет их по возрасту. Если на filesystem
осталось меньше `BACKUP_MIN_FREE_BYTES`, новый dump не создаётся. По умолчанию
порог равен 5 GiB.

При ошибке скрипт возвращает ненулевой exit code, пишет в syslog и пытается
отправить текст ошибки в тот же Telegram chat. Если недоступен сам Telegram,
сообщение останется только в syslog и cron output.

## Ручное восстановление

Скачайте manifest и все перечисленные в нём документы в один закрытый каталог.
Manifest должен быть сообщением, отправленным после всех частей. Не смешивайте
файлы от разных backup IDs.

Возьмите checkout репозитория, соответствующий `migration_version` из manifest.
Поднимите чистую PostgreSQL 17, примените все миграции и убедитесь, что domain
tables пусты. Затем выполните:

```sh
DATABASE_URL='postgres://operator:password@127.0.0.1:5432/gkfeed?sslmode=disable' \
    scripts/restore-postgres-backup.sh \
    /private/download/gkfeed-YYYYmmddTHHMMSSZ.manifest
```

Restore-скрипт проверит размеры и SHA-256 файлов, при необходимости склеит
части, проверит TOC и совпадение последней миграции. Он откажется работать с
непустой целевой базой. Затем он восстановит table data и sequence states в
одной транзакции, не меняя уже применённый `schema_migrations`.

После восстановления оператор создаёт application LOGIN identities вне Git и
проводит smoke checks API и parser по `docs/application-roles.md`.
