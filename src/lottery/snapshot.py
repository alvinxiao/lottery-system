import csv
import hashlib
import io
import json
from pathlib import Path

from .domain import Category, Class, Config, Proposal, Snapshot, ValidationError, validate


REQUIRED_FILES = ("classes.csv", "approved_proposals.csv")
CONFIG_FIELDS = {"schema_version", "event_id", "class_count", "game_target", "food_target", "snapshot_created_at", "approval_ids", "hash_manifest"}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"Duplicate JSON key {key}")
        result[key] = value
    return result


def _rows(data: bytes, fields: list[str]) -> list[dict[str, str]]:
    text = data.decode('utf-8')
    if '\r' in text or not text.endswith('\n'):
        raise ValidationError("CSV must use UTF-8 with LF and a final newline")
    reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
    if reader.fieldnames != fields:
        raise ValidationError(f"Expected CSV columns {','.join(fields)}")
    rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValidationError("CSV row has wrong number of columns")
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    if output.getvalue() != text:
        raise ValidationError("CSV must use canonical minimal quoting")
    return rows


def load_snapshot(directory: str | Path) -> Snapshot:
    try:
        root = Path(directory)
        config_path = root / 'config.json'
        if config_path.is_symlink():
            raise ValidationError("Snapshot files cannot be symbolic links")
        config_bytes = config_path.read_bytes()
        raw = json.loads(config_bytes, object_pairs_hook=_object)
        if not isinstance(raw, dict) or set(raw) != CONFIG_FIELDS:
            raise ValidationError("config.json has missing or unknown fields")
        if canonical_json(raw) != config_bytes:
            raise ValidationError("config.json must use canonical sorted compact JSON with final LF")
        manifest = raw.pop('hash_manifest')
        expected = set(REQUIRED_FILES)
        if isinstance(manifest, dict) and 'booths.csv' in manifest:
            expected.add('booths.csv')
        if not isinstance(manifest, dict) or set(manifest) != expected:
            raise ValidationError("Hash manifest must list exactly the supported snapshot CSV files")
        files = {}
        for name in sorted(expected):
            path = root / name
            if path.is_symlink():
                raise ValidationError("Snapshot files cannot be symbolic links")
            files[name] = path.read_bytes()
            if hashlib.sha256(files[name]).hexdigest() != manifest[name]:
                raise ValidationError(f"SHA-256 mismatch for {name}")
        if not isinstance(raw['approval_ids'], list) or any(not isinstance(s, str) for s in raw['approval_ids']):
            raise ValidationError("approval_ids must be an array of administrator IDs")
        raw['approval_ids'] = tuple(raw['approval_ids'])
        classes = tuple(Class(**row) for row in _rows(files['classes.csv'], ['class_id', 'display_name']))
        proposals = []
        for row in _rows(files['approved_proposals.csv'], ['class_id', 'rank', 'proposal_id', 'booth_id', 'category']):
            if row['rank'] not in ('1', '2', '3'):
                raise ValidationError("Ranks must be 1, 2, or 3")
            proposals.append(Proposal(**(row | {'rank': int(row['rank']), 'category': Category(row['category'])})))
        snapshot = Snapshot(classes, tuple(proposals), Config(**raw), hashlib.sha256(config_bytes).hexdigest())
        validate(snapshot)
        if 'booths.csv' in files:
            catalog = _rows(files['booths.csv'], ['booth_id', 'canonical_name', 'category'])
            expected_booths = {p.booth_id: p.category.value for p in proposals}
            if len(catalog) != len(expected_booths) or {r['booth_id']: r['category'] for r in catalog} != expected_booths:
                raise ValidationError("Booth catalog must match proposal IDs and categories exactly")
            if any(not r['canonical_name'].strip() or r['canonical_name'] != r['canonical_name'].strip() or any(ord(ch) < 32 for ch in r['canonical_name']) or r['canonical_name'].startswith(('=', '+', '-', '@')) for r in catalog):
                raise ValidationError("Booth names must be nonempty and spreadsheet safe")
        return snapshot
    except ValidationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, csv.Error, UnicodeError) as exc:
        raise ValidationError(f"Cannot load snapshot: {exc}") from exc
