"""Pure conversion rules for the temporary importer; no database writes."""

import base64
import binascii
import os
import re


class NormalizationError(Exception):
    """Only fixed, safe messages belong in this exception."""


def password_category(value):
    if value is None:
        return "null"
    if not isinstance(value, str):
        return "malformed_or_unsupported"
    # Reserve common encoded-password markers. Never rehash them as plaintext.
    if not value.startswith(("$", "{", "argon2", "pbkdf2", "scrypt", "bcrypt")):
        return "legacy_plaintext"
    parts = value.split("$")
    try:
        if len(parts) != 6 or parts[:3] != ["", "argon2id", "v=19"]:
            raise ValueError
        params = {}
        for field in parts[3].split(","):
            key, number = field.split("=")
            if key not in ("m", "t", "p") or key in params or not re.fullmatch(r"[0-9]+", number):
                raise ValueError
            params[key] = int(number)
            if not 0 < params[key] <= 2**32 - 1:
                raise ValueError
        if set(params) != {"m", "t", "p"} or params["p"] > 255 or params["m"] < 8 * params["p"]:
            raise ValueError
        for component in parts[4:]:
            if not re.fullmatch(r"[A-Za-z0-9+/]+", component):
                raise ValueError
            if not base64.b64decode(component + "=" * (-len(component) % 4), validate=True):
                raise ValueError
    except (ValueError, binascii.Error):
        return "malformed_or_unsupported"
    return "supported_argon2id"


def normalize_password(value):
    category = password_category(value)
    if category in ("null", "supported_argon2id"):
        return value
    if category != "legacy_plaintext":
        raise NormalizationError("Malformed or unsupported password representation.")
    from argon2.low_level import Type, hash_secret

    return hash_secret(value.encode("utf-8"), os.urandom(16), time_cost=3,
                       memory_cost=65536, parallelism=4, hash_len=32,
                       type=Type.ID, version=19).decode("ascii")


def remap_item(row, mapping):
    """Return the complete item with its normalized feed ID, ready for I07."""
    if row["feed_id"] not in mapping:
        raise NormalizationError("An item references a missing feed.")
    return dict(row, feed_id=mapping[row["feed_id"]])


def feed_plan(connection, present):
    rows = list(connection.execute('SELECT id, title, url, type, user_id FROM feed ORDER BY id'))
    mapping, preserved, groups = {}, [], {}
    for row in rows:
        feed_id, title, url, kind, user_id = row
        if type(feed_id) is not int or feed_id in mapping or type(user_id) is not int or any(
            not isinstance(value, str) for value in (title, url, kind)
        ):
            raise NormalizationError("Feed normalization requires unique integer IDs and complete rows.")
        key = (user_id, url, kind)
        if key not in groups:
            groups[key] = []
            preserved.append(dict(zip(("id", "title", "url", "type", "user_id"), row)))
        groups[key].append(feed_id)
        mapping[feed_id] = groups[key][0]

    # Read metadata with bound table names, including unknown names. Never report them.
    for table in present:
        columns = {row[1].lower() for row in connection.execute('SELECT * FROM pragma_table_info(?)', (table,))}
        foreign_keys = list(connection.execute('SELECT * FROM pragma_foreign_key_list(?)', (table,)))
        references = [fk for fk in foreign_keys if fk[2].lower() == 'feed']
        if table == 'item':
            if any(fk[3].lower() != 'feed_id' or fk[4] not in (None, 'id') for fk in references):
                raise NormalizationError("Source contains a feed dependency without a safe remapping rule.")
        elif table in {'feed_parser', 'item_hash', 'item_hash_new'}:
            # I07 has explicit merge policies for parser state. item_hash_new is
            # a strictly validated, excluded source-only artifact.
            continue
        elif 'feed_id' in columns or references:
            raise NormalizationError("Source contains a feed dependency without a safe remapping rule.")
        elif table not in {'users', 'feed', 'deleted_items', 'itemhash', 'auth_refresh_tokens',
                           'webauthn_credentials', 'refresh_tokens', 'log'}:
            # Undeclared references in unknown tables cannot be ruled out.
            raise NormalizationError("Source contains an unrecognized table without a dependency policy.")

    remapped_items = 0
    orphan_items = 0
    for (feed_id,) in connection.execute('SELECT feed_id FROM item'):
        if feed_id not in mapping:
            orphan_items += 1
            continue
        remapped = remap_item({'feed_id': feed_id}, mapping)
        remapped_items += remapped['feed_id'] != feed_id
    duplicate_groups = [ids for ids in groups.values() if len(ids) > 1]
    report = {
        'source_count': len(rows), 'group_count': len(groups),
        'duplicate_group_count': len(duplicate_groups),
        'duplicate_source_rows': sum(map(len, duplicate_groups)),
        'merged_count': len(rows) - len(preserved), 'expected_target_count': len(preserved),
        'id_mapping': [{'old_id': old, 'preserved_id': new} for old, new in mapping.items()],
        'items_to_remap': remapped_items,
        'orphan_items': orphan_items,
    }
    return report, preserved, mapping
