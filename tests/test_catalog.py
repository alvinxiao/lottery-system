import hashlib
import json

import pytest

from lottery.domain import ValidationError
from lottery.snapshot import canonical_json, load_snapshot
from helpers import sample, write_snapshot


@pytest.mark.parametrize('catalog,valid', [
    ('a,Archery,game\nb,Baking,food\nc,Cookies,food\n', True),
    ('a,Archery,food\nb,Baking,food\nc,Cookies,food\n', False),
    ('a,Archery,game\nb,Baking,food\nb,Cookies,food\n', False),
    ('a,=FORMULA(),game\nb,Baking,food\nc,Cookies,food\n', False),
    ('a,\t=FORMULA(),game\nb,Baking,food\nc,Cookies,food\n', False),
])
def test_optional_catalog_contract(tmp_path, catalog, valid):
    snapshot = sample([[('a', 'game'), ('b', 'food'), ('c', 'food')]], 1)
    root = write_snapshot(tmp_path, snapshot)
    data = ('booth_id,canonical_name,category\n' + catalog).encode()
    (root / 'booths.csv').write_bytes(data)
    config = json.loads((root / 'config.json').read_bytes())
    config['hash_manifest']['booths.csv'] = hashlib.sha256(data).hexdigest()
    (root / 'config.json').write_bytes(canonical_json(config))
    if valid:
        assert load_snapshot(root).proposals == snapshot.proposals
    else:
        with pytest.raises(ValidationError):
            load_snapshot(root)
