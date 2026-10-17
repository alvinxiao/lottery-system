from collections import Counter
from collections.abc import Sequence

from .domain import Assignment, Category, Snapshot, ValidationError, validate


def verify_assignments(snapshot: Snapshot, assignments: Sequence[Assignment]) -> None:
    validate(snapshot)
    if any(type(a.assigned_rank) is not int or not isinstance(a.category, Category) for a in assignments):
        raise ValidationError('Result rank and category have invalid types')
    if Counter(a.class_id for a in assignments) != Counter(c.class_id for c in snapshot.classes):
        raise ValidationError("Result must assign every class exactly once")
    if len({a.booth_id for a in assignments}) != len(assignments):
        raise ValidationError("Result assigns a booth more than once")
    approved = {(p.class_id, p.booth_id, p.category, p.rank) for p in snapshot.proposals}
    if any((a.class_id, a.booth_id, a.category, a.assigned_rank) not in approved for a in assignments):
        raise ValidationError("Result contains an unapproved choice, category, or rank")
    totals = Counter(a.category for a in assignments)
    if totals[Category.GAME] != snapshot.config.game_target or totals[Category.FOOD] != snapshot.config.food_target:
        raise ValidationError("Result does not satisfy category quotas")


def evaluate_objectives(snapshot: Snapshot, assignments: Sequence[Assignment], priority: Sequence[str]) -> tuple[int, ...]:
    from .priority import manual_priority
    verify_assignments(snapshot, assignments)
    order = manual_priority([c.class_id for c in snapshot.classes], priority)
    by_class = {a.class_id: a for a in assignments}
    unique_first = sum(a.assigned_rank == 1 and not any(p.class_id != a.class_id and p.booth_id == a.booth_id for p in snapshot.proposals) for a in assignments)
    return (unique_first, sum(a.assigned_rank == 1 for a in assignments), sum(a.assigned_rank == 2 for a in assignments), *(-by_class[cid].assigned_rank for cid in order))


def verify_solution(snapshot: Snapshot, assignments: Sequence[Assignment], priority: Sequence[str], objective_vector: Sequence[int]) -> None:
    if any(type(value) is not int for value in objective_vector):
        raise ValidationError('Reported objective vector must contain integers')
    if tuple(objective_vector) != evaluate_objectives(snapshot, assignments, priority):
        raise ValidationError('Reported objective vector disagrees with assignments')
