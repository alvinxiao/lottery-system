from datetime import datetime
from dataclasses import dataclass
from enum import StrEnum


class ValidationError(ValueError):
    pass


class Category(StrEnum):
    GAME = "game"
    FOOD = "food"


@dataclass(frozen=True)
class Class:
    class_id: str
    display_name: str


@dataclass(frozen=True)
class Proposal:
    class_id: str
    rank: int
    proposal_id: str
    booth_id: str
    category: Category


@dataclass(frozen=True)
class Config:
    schema_version: int
    event_id: str
    class_count: int
    game_target: int
    food_target: int
    snapshot_created_at: str
    approval_ids: tuple[str, ...]


@dataclass(frozen=True)
class Snapshot:
    classes: tuple[Class, ...]
    proposals: tuple[Proposal, ...]
    config: Config
    input_hash: str


@dataclass(frozen=True)
class Assignment:
    class_id: str
    booth_id: str
    category: Category
    assigned_rank: int


def validate(snapshot: Snapshot) -> None:
    config = snapshot.config
    try:
        timestamp = datetime.fromisoformat(config.snapshot_created_at.replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError('missing timezone')
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError('snapshot_created_at must be an ISO-8601 timestamp with a timezone') from exc
    ids = [c.class_id for c in snapshot.classes]
    if not ids or len(ids) != len(set(ids)):
        raise ValidationError("Class IDs must be nonempty and unique")
    if type(config.schema_version) is not int or config.schema_version != 1:
        raise ValidationError("Only schema_version 1 is supported")
    counts = (config.class_count, config.game_target, config.food_target)
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValidationError("Counts and quotas must be nonnegative integers")
    if config.class_count != len(ids) or sum(counts[1:]) != len(ids):
        raise ValidationError("Class count and category quotas must match the roster")
    if len(config.approval_ids) < 2 or len(set(config.approval_ids)) != len(config.approval_ids):
        raise ValidationError("At least two distinct approval IDs are required")
    booths: dict[str, Category] = {}
    proposal_ids: set[str] = set()
    for p in snapshot.proposals:
        if p.class_id not in ids or type(p.rank) is not int or p.rank not in (1, 2, 3):
            raise ValidationError("Proposal has unknown class or invalid rank")
        if not isinstance(p.category, Category):
            raise ValidationError("Category must be game or food")
        if p.proposal_id in proposal_ids:
            raise ValidationError("Proposal IDs must be globally unique")
        proposal_ids.add(p.proposal_id)
        if p.booth_id in booths and booths[p.booth_id] != p.category:
            raise ValidationError("A booth ID has inconsistent categories")
        booths[p.booth_id] = p.category
    for cid in ids:
        choices = [p for p in snapshot.proposals if p.class_id == cid]
        if sorted(p.rank for p in choices) != [1, 2, 3] or len({p.booth_id for p in choices}) != 3:
            raise ValidationError(f"Class {cid} needs exactly ranks 1, 2, 3 with distinct booth IDs")
    strings = [config.event_id, *config.approval_ids]
    strings += [s for c in snapshot.classes for s in (c.class_id, c.display_name)]
    strings += [s for p in snapshot.proposals for s in (p.class_id, p.booth_id, p.proposal_id)]
    if any(not isinstance(s, str) or not s.strip() or s != s.strip() or any(ord(ch) < 32 for ch in s) or s.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) for s in strings):
        raise ValidationError("Text must be nonempty, trimmed, and safe for spreadsheet import")
