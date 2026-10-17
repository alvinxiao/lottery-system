import hashlib
import json
from dataclasses import replace
import subprocess
import sys
import pytest
from lottery.domain import ValidationError, validate
from lottery.priority import automatic_priority, manual_priority, new_seed
from lottery.snapshot import canonical_json, load_snapshot
from helpers import sample, write_snapshot


@pytest.fixture
def snapshot():
    return sample([[('a', 'game'), ('b', 'food'), ('c', 'food')]], 1)


def mutate_config(root, update):
    config = json.loads((root/'config.json').read_bytes())
    update(config)
    (root/'config.json').write_bytes(canonical_json(config))


def test_valid_snapshot_and_real_cli(tmp_path, snapshot):
    root = write_snapshot(tmp_path, snapshot)
    actual = load_snapshot(root)
    assert actual.classes == snapshot.classes
    for command in ['validate', 'feasibility']:
        result = subprocess.run([sys.executable, '-m', 'lottery.cli', command, str(root)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['nonofficial']


@pytest.mark.parametrize('update', [
    lambda c: c.update(class_count=True), lambda c: c.update(game_target=-1),
    lambda c: c.update(food_target=1), lambda c: c.update(class_count=2),
    lambda c: c.update(schema_version=2), lambda c: c.update(schema_version=True), lambda c: c.update(approval_ids=['a']),
    lambda c: c.update(approval_ids=['a', 'a']), lambda c: c.update(approval_ids=['a', 2]),
    lambda c: c.update(approval_ids='ab'), lambda c: c.update(extra=1),
    lambda c: c.update(snapshot_created_at='2026-01-01'),
    lambda c: c['hash_manifest'].update({'../outside': 'x'}),
    lambda c: c['hash_manifest'].update({'config.json': 'x'}),
])
def test_invalid_configuration(tmp_path, snapshot, update):
    root = write_snapshot(tmp_path, snapshot)
    mutate_config(root, update)
    with pytest.raises(ValidationError):
        load_snapshot(root)


@pytest.mark.parametrize('old,new', [
    ('c0,1,p0_1,a,game', 'c0,1,p0_1,a,invalid'),
    ('c0,2,p0_2,b,food', 'c0,1,p0_2,b,food'),
    ('c0,2,p0_2,b,food', 'c0,2,p0_2,a,game'),
    ('c0,2,p0_2,b,food', 'c0,2,p0_1,b,food'),
    ('class_id,rank,proposal_id,booth_id,category', 'class_id,rank,rank,booth_id,category'),
    ('c0,2,p0_2,b,food', 'unknown,2,p0_2,b,food'),
    ('c0,2,p0_2,b,food', 'c0,2,p0_2,,food'),
])
def test_invalid_csv_even_with_matching_hash(tmp_path, snapshot, old, new):
    root = write_snapshot(tmp_path, snapshot)
    path = root/'approved_proposals.csv'
    path.write_bytes(path.read_bytes().replace(old.encode(), new.encode()))
    mutate_config(root, lambda c: c['hash_manifest'].update({'approved_proposals.csv': hashlib.sha256(path.read_bytes()).hexdigest()}))
    with pytest.raises(ValidationError):
        load_snapshot(root)


def test_tampered_hash_duplicate_keys_and_symlink(tmp_path, snapshot):
    root = write_snapshot(tmp_path, snapshot)
    path = root/'classes.csv'
    path.write_bytes(path.read_bytes()+b'c2,Other\n')
    with pytest.raises(ValidationError, match='SHA-256'):
        load_snapshot(root)
    write_snapshot(root, snapshot)
    config = root/'config.json'
    config.write_bytes(config.read_bytes().replace(b'{', b'{"event_id":"duplicate",', 1))
    with pytest.raises(ValidationError, match='Duplicate JSON'):
        load_snapshot(root)


def test_category_conflict_and_duplicate_classes(snapshot):
    with pytest.raises(ValidationError):
        validate(replace(snapshot, classes=snapshot.classes*2))
    other = sample([[('a', 'game'), ('b', 'food'), ('c', 'food')], [('a', 'food'), ('d', 'food'), ('e', 'food')]], 1)
    with pytest.raises(ValidationError, match='inconsistent'):
        validate(other)


def test_priority_replay_manual_and_seed_validation():
    ids = ['c0', 'c1', 'c2', 'c3']
    seed = '00'*32
    assert automatic_priority(ids, seed) == ('c2', 'c3', 'c0', 'c1')
    assert automatic_priority(ids, seed) == automatic_priority(ids[::-1], seed)
    assert set(automatic_priority(ids, new_seed())) == set(ids)
    assert manual_priority(ids, ids[::-1]) == tuple(ids[::-1])
    for order in [ids[:-1], ['c0']*4, ids+['x']]:
        with pytest.raises(ValidationError):
            manual_priority(ids, order)
    for seed in ['', 'z'*64, 'AA'*32]:
        with pytest.raises(ValidationError):
            automatic_priority(ids, seed)


def test_symlink_input_rejected(tmp_path, snapshot):
    root = write_snapshot(tmp_path/'snapshot', snapshot)
    original = root/'classes.csv'
    target = tmp_path/'original.csv'
    original.rename(target)
    try:
        original.symlink_to(target)
    except OSError:
        pytest.skip('Symlink creation unavailable on this platform')
    with pytest.raises(ValidationError, match='symbolic'):
        load_snapshot(root)


def test_cli_invalid_and_infeasible_statuses(tmp_path, snapshot):
    root = write_snapshot(tmp_path, snapshot)
    mutate_config(root, lambda c: c.update(game_target=0, food_target=1))
    path = root/'approved_proposals.csv'
    path.write_bytes(path.read_bytes().replace(b'food', b'game'))
    mutate_config(root, lambda c: c['hash_manifest'].update({'approved_proposals.csv': hashlib.sha256(path.read_bytes()).hexdigest()}))
    result = subprocess.run([sys.executable, '-m', 'lottery.cli', 'feasibility', str(root)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['status'] == 'INFEASIBLE'
    mutate_config(root, lambda c: c.update(class_count=4))
    result = subprocess.run([sys.executable, '-m', 'lottery.cli', 'validate', str(root)], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'Class count' in result.stderr
