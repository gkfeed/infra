# I12 — Удалить SQLite importer после cutover

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: отсутствует; см. внешние предусловия ниже

## Предусловия

- Cutover завершён.
- Работа PostgreSQL подтверждена.
- Владелец явно решил удалить legacy tooling.

## Цель

Удалить завершивший работу временный SQLite importer, сохранив историю
PostgreSQL-контракта.

## План

- [ ] Удалить `legacy-import/`, его зависимости и команды.
- [ ] Оставить историческую запись о выполненном переносе в runbook или release
      notes.
- [ ] Не удалять SQL-миграции, `schema.sql` или migration policy.

## Готово, когда

Постоянный infra содержит только PostgreSQL-контракт и не зависит от
SQLite/Python importer.
