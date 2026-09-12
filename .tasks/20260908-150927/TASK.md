# I14: Add hourly PostgreSQL backups to Telegram

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [I13](../20260908-150926/TASK.md)

## Goal

Replace the legacy hourly SQLite export with a PostgreSQL 17 backup owned by
this repository. Keep a complete logical dump off-host in Telegram and provide
a tested manual recovery path.

The agreed recovery targets are an RPO of one hour and an RTO of four hours.

## Accepted constraints

- Telegram is the only off-host destination and keeps messages without
  automated retention.
- Backups are not encrypted before upload. Telegram Bot API chats do not
  provide end-to-end encryption, so Telegram and anyone with the bot token can
  access the database archive.
- Restore is manual. There is no scheduled restore rehearsal after the initial
  local validation.
- The production cron entry and LOGIN identity are operator-managed and remain
  outside Git.

## Plan

- [x] Agree on an hourly schedule, one-hour RPO, four-hour RTO, Telegram
      storage, no automatic retention, and one initial restore test.
- [x] Add a least-privilege `gkfeed_backup NOLOGIN` group role through a
      forward migration. The operator creates its LOGIN identity outside Git.
- [x] Create a complete PostgreSQL 17 custom dump with no owners or ACLs.
- [x] Verify the archive TOC and record its size and SHA-256 in a commit
      manifest.
- [x] Split archives into payloads no larger than 45,000,000 bytes and send the
      manifest only after every payload reaches Telegram.
- [x] Keep failed uploads in a private host spool and resume them on the next
      run. Never delete an uncommitted backup automatically.
- [x] Refuse to create another archive when the spool filesystem has less than
      5 GiB free.
- [x] Provide a minute-five cron entry using `flock` and report failures to
      syslog, cron output, and Telegram when Telegram remains reachable.
- [x] Document server setup and manual recovery into a clean migrated
      PostgreSQL 17 database.
- [x] Restore a fresh production archive into a disposable PostgreSQL 17 on the
      operator workstation, verify table counts, record the elapsed time, and
      remove the local production data afterward.
- [x] Install and verify the production cron entry.

## Definition of done

An hourly production run creates a complete custom archive, sends every
payload and its final manifest to Telegram, and removes local data only after
Telegram confirms the manifest. Failures leave a resumable local copy and
notify the operator. A clean local restore proves the documented manual
procedure within the four-hour RTO.

## Validation

Keep this task pending until I13 is done. Record production results without
recording credentials, connection URLs, chat IDs, or database contents.

On 2026-09-12 the operator applied migration `20260911093048`, provisioned the
private environment and separate `gkfeed_backup_login` identity, and installed
the minute-five cron entry. The initial manual run committed
`gkfeed-20260912T101827Z`: a 95,645,407-byte archive split into three payloads
with its manifest sent last. The local pending queue was empty afterward.

The first four scheduled runs at 11:05, 12:05, 13:05, and 14:05 UTC all
committed their Telegram manifests and completed without logged errors. The
pending queue remained empty. The legacy SQLite backup cron entry was removed,
no legacy backup process remained, and the cron service was active with exactly
one PostgreSQL backup entry.

The three migrations applied in strict order to disposable PostgreSQL 17, and
both application and backup role checks passed. A fresh production archive was
restored into a migrated local source, backed up through the new script, and
restored into a second clean migrated cluster. The seven table counts and four
sequence states matched. The clean restore took three seconds, well inside the
four-hour RTO.

The upload test forced one-megabyte parts, producing 19 payloads. The manifest
was sent last and the successful queue was removed. A second test rejected the
third payload: the complete backup remained pending with two sent markers, and
the next run resumed it and emptied the queue. A repeated restore into the
populated target was rejected. A separate fixture round trip covered the normal
single-document path. All temporary containers, archives, restored data,
credentials, and fake Telegram output were removed after validation.
