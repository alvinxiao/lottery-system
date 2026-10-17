import hashlib
import secrets
from collections.abc import Sequence

from .domain import ValidationError


ALGORITHM_VERSION = 'sha256-counter-fisher-yates-v1'


def manual_priority(class_ids: Sequence[str], order: Sequence[str]) -> tuple[str, ...]:
    if len(class_ids) != len(set(class_ids)) or len(order) != len(class_ids) or set(order) != set(class_ids):
        raise ValidationError("Priority must contain every class ID exactly once")
    return tuple(order)


def new_seed() -> str:
    return secrets.token_hex(32)


def automatic_priority(class_ids: Sequence[str], seed: str) -> tuple[str, ...]:
    if not isinstance(seed, str) or len(seed) != 64 or any(c not in '0123456789abcdef' for c in seed):
        raise ValidationError("Seed must be 64 lowercase hexadecimal characters")
    values = sorted(class_ids)
    manual_priority(values, values)
    key = bytes.fromhex(seed)
    counter = 0
    for i in range(len(values) - 1, 0, -1):
        limit = (1 << 256) - ((1 << 256) % (i + 1))
        while True:
            number = int.from_bytes(hashlib.sha256(key + counter.to_bytes(16, 'big')).digest(), 'big')
            counter += 1
            if number < limit:
                break
        j = number % (i + 1)
        values[i], values[j] = values[j], values[i]
    return tuple(values)
