import argparse
import json
import sys
from dataclasses import asdict
from .domain import ValidationError
from .snapshot import load_snapshot
from .solver import SolveIncomplete, feasibility


def main() -> int:
    parser = argparse.ArgumentParser(description='NONOFFICIAL snapshot validation and deterministic feasibility. No draw is performed.')
    parser.add_argument('command', choices=['validate', 'feasibility'])
    parser.add_argument('snapshot', help='Version-1 snapshot directory')
    parser.add_argument('--time-limit', type=float, default=None)
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(args.snapshot)
        result = {'nonofficial': True, 'snapshot_hash': snapshot.input_hash, 'valid': True}
        if args.command == 'feasibility':
            report = feasibility(snapshot, time_limit=args.time_limit)
            result.update(asdict(report))
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('feasible', True) else 1
    except (ValidationError, SolveIncomplete, ValueError) as exc:
        print(f'Cannot complete {args.command}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
