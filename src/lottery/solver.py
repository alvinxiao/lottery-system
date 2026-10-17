import math
from dataclasses import dataclass
from collections.abc import Sequence
from ortools.sat.python import cp_model

from .domain import Assignment, Category, Snapshot, validate
from .priority import manual_priority
from .verify import verify_solution


class SolveIncomplete(RuntimeError):
    pass


class Infeasible(RuntimeError):
    pass


@dataclass(frozen=True)
class Feasibility:
    feasible: bool
    status: str
    correction_candidates: tuple[str, ...]


@dataclass(frozen=True)
class Solution:
    assignments: tuple[Assignment, ...]
    objective_vector: tuple[int, ...]
    status: str


def _model(snapshot: Snapshot):
    validate(snapshot)
    model = cp_model.CpModel()
    variables = [model.new_bool_var(f'choice_{i}') for i in range(len(snapshot.proposals))]
    for cls in snapshot.classes:
        model.add(sum(v for v, p in zip(variables, snapshot.proposals) if p.class_id == cls.class_id) == 1)
    for booth in sorted({p.booth_id for p in snapshot.proposals}):
        model.add(sum(v for v, p in zip(variables, snapshot.proposals) if p.booth_id == booth) <= 1)
    for category, quota in ((Category.GAME, snapshot.config.game_target), (Category.FOOD, snapshot.config.food_target)):
        model.add(sum(v for v, p in zip(variables, snapshot.proposals) if p.category == category) == quota)
    return model, variables


def _solver(time_limit: float | None):
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    if time_limit is not None:
        if not math.isfinite(time_limit) or time_limit <= 0:
            raise ValueError('time_limit must be finite and positive')
        solver.parameters.max_time_in_seconds = time_limit
    return solver


def feasibility(snapshot: Snapshot, *, time_limit: float | None = None) -> Feasibility:
    model, _ = _model(snapshot)
    solver = _solver(time_limit)
    status = solver.solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Feasibility(True, solver.status_name(status), ())
    if status == cp_model.INFEASIBLE:
        return Feasibility(False, 'INFEASIBLE', tuple(sorted(c.class_id for c in snapshot.classes)))
    raise SolveIncomplete(f'Feasibility not established: {solver.status_name(status)}. Retry with a larger time limit.')


def optimize(snapshot: Snapshot, priority: Sequence[str], *, time_limit: float | None = None) -> Solution:
    model, variables = _model(snapshot)
    order = manual_priority([c.class_id for c in snapshot.classes], priority)
    owners: dict[str, set[str]] = {}
    for p in snapshot.proposals:
        owners.setdefault(p.booth_id, set()).add(p.class_id)
    objectives = [sum(v for v, p in zip(variables, snapshot.proposals) if p.rank == 1 and len(owners[p.booth_id]) == 1)]
    objectives += [sum(v for v, p in zip(variables, snapshot.proposals) if p.rank == rank) for rank in (1, 2)]
    objectives += [-sum(p.rank * v for v, p in zip(variables, snapshot.proposals) if p.class_id == cid) for cid in order]
    solver = _solver(time_limit)
    values = []
    for expression in objectives:
        model.maximize(expression)
        status = solver.solve(model)
        if status == cp_model.INFEASIBLE:
            raise Infeasible('No full assignment meets uniqueness and category quotas')
        if status != cp_model.OPTIMAL:
            raise SolveIncomplete(f'Optimality not proved: {solver.status_name(status)}. No allocation returned.')
        optimum = solver.value(expression)
        values.append(optimum)
        model.add(expression == optimum)
    assignments = tuple(sorted((Assignment(p.class_id, p.booth_id, p.category, p.rank) for v, p in zip(variables, snapshot.proposals) if solver.value(v)), key=lambda a: a.class_id))
    verify_solution(snapshot, assignments, order, values)
    return Solution(assignments, tuple(values), 'OPTIMAL')
