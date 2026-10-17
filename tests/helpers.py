import csv
import hashlib
import io
from pathlib import Path
from lottery.domain import Category, Class, Config, Proposal, Snapshot
from lottery.snapshot import canonical_json


def sample(choices, games):
    classes = tuple(Class(f'c{i}', f'Class {i}') for i in range(len(choices)))
    proposals = tuple(Proposal(f'c{i}', rank, f'p{i}_{rank}', booth, Category(category)) for i, row in enumerate(choices) for rank, (booth, category) in enumerate(row, 1))
    return Snapshot(classes, proposals, Config(1, 'test-event', len(classes), games, len(classes)-games, '2026-01-01T00:00:00Z', ('admin-a', 'admin-b')), 'synthetic')


def write_snapshot(root: Path, snapshot):
    root.mkdir(parents=True, exist_ok=True)
    datasets = {
        'classes.csv': (['class_id', 'display_name'], [[c.class_id, c.display_name] for c in snapshot.classes]),
        'approved_proposals.csv': (['class_id', 'rank', 'proposal_id', 'booth_id', 'category'], [[p.class_id, p.rank, p.proposal_id, p.booth_id, p.category.value] for p in snapshot.proposals]),
    }
    manifest = {}
    for name, (header, rows) in datasets.items():
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)
        data = stream.getvalue().encode()
        (root/name).write_bytes(data)
        manifest[name] = hashlib.sha256(data).hexdigest()
    config = {key: getattr(snapshot.config, key) for key in snapshot.config.__dataclass_fields__}
    config['approval_ids'] = list(config['approval_ids'])
    config['hash_manifest'] = manifest
    (root/'config.json').write_bytes(canonical_json(config))
    return root
