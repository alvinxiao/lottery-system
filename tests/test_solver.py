import itertools
from dataclasses import replace
import pytest
from hypothesis import given, settings, strategies as st
from lottery.domain import Assignment, Category, ValidationError
from lottery.solver import Infeasible, feasibility, optimize
from lottery.verify import verify_assignments
from helpers import sample


def oracle(snapshot, order):
    groups = [[p for p in snapshot.proposals if p.class_id == cid] for cid in order]
    solutions = []
    for selected in itertools.product(*groups):
        if len({p.booth_id for p in selected}) != len(selected):
            continue
        if sum(p.category == Category.GAME for p in selected) != snapshot.config.game_target:
            continue
        unique = sum(p.rank == 1 and not any(q.class_id != p.class_id and q.booth_id == p.booth_id for q in snapshot.proposals) for p in selected)
        score = (unique, sum(p.rank == 1 for p in selected), sum(p.rank == 2 for p in selected), *(-p.rank for p in selected))
        solutions.append((score, {(p.class_id, p.booth_id) for p in selected}))
    return max(solutions, key=lambda item: item[0]) if solutions else None


@st.composite
def cases(draw):
    count = draw(st.integers(1, 5))
    categories = draw(st.lists(st.sampled_from(['game', 'food']), min_size=6, max_size=6))
    rows = []
    for _ in range(count):
        booths = draw(st.lists(st.integers(0, 5), min_size=3, max_size=3, unique=True))
        rows.append([(f'b{b}', categories[b]) for b in booths])
    return sample(rows, draw(st.integers(0, count)))


@given(cases())
@settings(max_examples=65, deadline=None, derandomize=True)
def test_exact_objective_against_independent_exhaustive_oracle(snapshot):
    order = tuple(reversed([c.class_id for c in snapshot.classes]))
    expected = oracle(snapshot, order)
    assert feasibility(snapshot).feasible == (expected is not None)
    if expected is None:
        with pytest.raises(Infeasible):
            optimize(snapshot, order)
    else:
        actual = optimize(snapshot, order)
        assert actual.objective_vector == expected[0]
        assert {(a.class_id, a.booth_id) for a in actual.assignments} == expected[1]
        reordered = replace(snapshot, classes=snapshot.classes[::-1], proposals=snapshot.proposals[::-1])
        assert optimize(reordered, order) == actual


def test_full_default_case_and_changed_quotas():
    choices = [[(f'g{i}', 'game'), (f'f{i}', 'food'), (f'x{i}', 'food')] for i in range(22)]
    snapshot = sample(choices, 9)
    result = optimize(snapshot, [c.class_id for c in snapshot.classes])
    verify_assignments(snapshot, result.assignments)
    assert len(result.assignments) == 22
    assert sum(a.category == Category.GAME for a in result.assignments) == 9
    changed = replace(snapshot, config=replace(snapshot.config, game_target=10, food_target=12))
    assert sum(a.category == Category.GAME for a in optimize(changed, [c.class_id for c in changed.classes]).assignments) == 10


def test_fourteen_food_only_with_thirteen_slots():
    rows = [[(f'f{i}_{j}', 'food') for j in range(3)] for i in range(14)]
    rows += [[(f'g{i}_{j}', 'game') for j in range(3)] for i in range(8)]
    snapshot = sample(rows, 9)
    report = feasibility(snapshot)
    assert report.status == 'INFEASIBLE'
    assert not report.feasible
    assert set(report.correction_candidates) == {c.class_id for c in snapshot.classes}


def test_unique_first_uses_other_classes_all_ranks():
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')], [('d', 'game'), ('a', 'game'), ('e', 'game')]], 2)
    result = optimize(snapshot, ['c0', 'c1'])
    assert result.objective_vector[:3] == (1, 2, 0)


def test_independent_verifier_rejects_bad_results():
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')]], 1)
    with pytest.raises(ValidationError):
        verify_assignments(snapshot, [])
    for assignment in [Assignment('c0', 'x', Category.GAME, 1), Assignment('c0', 'a', Category.FOOD, 1), Assignment('c0', 'a', Category.GAME, 2)]:
        with pytest.raises(ValidationError):
            verify_assignments(snapshot, [assignment])


def test_independent_objective_verifier():
    from lottery.verify import verify_solution
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')]], 1)
    actual = optimize(snapshot, ['c0'])
    verify_solution(snapshot, actual.assignments, ['c0'], actual.objective_vector)
    with pytest.raises(ValidationError):
        verify_solution(snapshot, actual.assignments, ['c0'], (0, 0, 0, 0))
    for invalid in [(True, 1, 0, -1), (1.0, 1, 0, -1)]:
        with pytest.raises(ValidationError):
            verify_solution(snapshot, actual.assignments, ['c0'], invalid)


def test_unknown_status_is_not_infeasibility(monkeypatch):
    import lottery.solver as module
    from ortools.sat.python import cp_model
    class UnknownSolver:
        def solve(self, model):
            return cp_model.UNKNOWN
        def status_name(self, status):
            return 'UNKNOWN'
    monkeypatch.setattr(module, '_solver', lambda limit: UnknownSolver())
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')]], 1)
    with pytest.raises(module.SolveIncomplete):
        feasibility(snapshot)
    with pytest.raises(module.SolveIncomplete):
        optimize(snapshot, ['c0'])


@pytest.mark.parametrize('limit', [0, -1, float('nan'), float('inf')])
def test_invalid_time_limits(limit):
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')]], 1)
    with pytest.raises(ValueError, match='finite and positive'):
        feasibility(snapshot, time_limit=limit)


def test_priority_decides_only_after_primary_objectives():
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')], [('a', 'game'), ('b', 'game'), ('d', 'game')]], 2)
    first = optimize(snapshot, ['c0', 'c1'])
    second = optimize(snapshot, ['c1', 'c0'])
    assert first.objective_vector[:3] == second.objective_vector[:3]
    assert first.assignments[0].assigned_rank == 1
    assert second.assignments[1].assigned_rank == 1


def test_result_types_are_strict():
    snapshot = sample([[('a', 'game'), ('b', 'game'), ('c', 'game')]], 1)
    for a in [Assignment('c0', 'a', Category.GAME, True), Assignment('c0', 'a', 'game', 1)]:
        with pytest.raises(ValidationError):
            verify_assignments(snapshot, [a])
