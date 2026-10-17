"""Generate fictional rehearsal input, never a priority draw or official result."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from lottery.snapshot import canonical_json


DEFAULT_EVENT = "DEMO-carnival-2026-rehearsal-01"
GAMES = (
    ("G01", "Ring toss"),
    ("G02", "Beanbag toss"),
    ("G03", "Balloon darts"),
    ("G04", "Duck pond"),
    ("G05", "Mini basketball"),
    ("G06", "Bottle knockdown"),
    ("G07", "Fishing pond"),
    ("G08", "Spin the wheel"),
    ("G09", "Mini golf"),
)
FOODS = (
    ("F01", "Jiaozi 饺子"),
    ("F02", "Baozi 包子"),
    ("F03", "Scallion pancakes 葱油饼"),
    ("F04", "Fried rice 炒饭"),
    ("F05", "Chow mein 炒面"),
    ("F06", "Wonton soup 馄饨汤"),
    ("F07", "Tangyuan 汤圆"),
    ("F08", "Egg tarts 蛋挞"),
    ("F09", "Tea eggs 茶叶蛋"),
    ("F10", "Spring rolls 春卷"),
    ("F11", "Sesame balls 芝麻球"),
    ("F12", "Tofu pudding 豆花"),
    ("F13", "Zhajiang noodles 炸酱面"),
)
CLASSES = tuple(
    (
        f"C{i:02}",
        f"Class {i:02} - {('Kindergarten', 'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4', 'Grade 5')[(i - 1) // 4]}",
    )
    for i in range(1, 23)
)


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def choices(infeasible=False):
    """Each row contains its own distinct booth, proving a feasible matching.

    Swap some first and second ranks to introduce shared first choices. In the
    negative fixture fourteen food-only classes exceed the thirteen food slots.
    """
    rows = []
    for index, (class_id, _) in enumerate(CLASSES):
        if infeasible:
            catalog = FOODS if index < 14 else GAMES
            offset = index % len(catalog)
            ids = [catalog[(offset + delta) % len(catalog)][0] for delta in (0, 1, 2)]
        else:
            catalog = GAMES if index < 9 else FOODS
            offset = index if index < 9 else index - 9
            own = catalog[offset][0]
            neighbor = catalog[(offset + 1) % len(catalog)][0]
            cross = FOODS[index % 13][0] if index < 9 else GAMES[index % 9][0]
            ids = [neighbor, own, cross] if index % 3 == 0 else [own, neighbor, cross]
        for rank, booth_id in enumerate(ids, 1):
            rows.append(
                (
                    class_id,
                    rank,
                    f"{class_id}-P{rank}",
                    booth_id,
                    "game" if booth_id.startswith("G") else "food",
                )
            )
    return rows


def snapshot_files(event_id, infeasible=False):
    proposals = choices(infeasible)
    used = {row[3] for row in proposals}
    booth_rows = [
        (bid, name, category)
        for catalog, category in ((GAMES, "game"), (FOODS, "food"))
        for bid, name in catalog
        if bid in used
    ]
    files = {
        "classes.csv": csv_bytes(["class_id", "display_name"], CLASSES),
        "approved_proposals.csv": csv_bytes(
            ["class_id", "rank", "proposal_id", "booth_id", "category"], proposals
        ),
        "booths.csv": csv_bytes(
            ["booth_id", "canonical_name", "category"], sorted(booth_rows)
        ),
    }
    config = dict(
        schema_version=1,
        event_id=event_id,
        class_count=22,
        game_target=9,
        food_target=13,
        snapshot_created_at="2026-10-17T12:00:00Z",
        approval_ids=["DEMO-admin-alex", "DEMO-admin-robin"],
        hash_manifest={
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        },
    )
    files["config.json"] = canonical_json(config)
    return files


def generated_files(event_id=DEFAULT_EVENT):
    result = {}
    for directory, bad in (("ready-to-draw", False), ("infeasible", True)):
        for name, data in snapshot_files(
            event_id + ("-infeasible" if bad else ""), bad
        ).items():
            result[f"{directory}/{name}"] = data
    # A supplied, fixed practice order. This function never generates randomness.
    result["manual-priority.txt"] = (
        "\n".join(class_id for class_id, _ in reversed(CLASSES)) + "\n"
    ).encode()
    names = dict(GAMES + FOODS)
    proposals = choices()
    intake = {
        "demo_only": True,
        "dry_run": True,
        "event_id": event_id,
        "administrators": [
            dict(admin_id=f"DEMO-admin-{name}", email=f"{name}@example.invalid")
            for name in ("alex", "robin")
        ],
        "classes": [
            dict(
                class_id=cid,
                display_name=display,
                contact_name=f"Fictional Parent {cid}",
                contact_email=f"parent-{cid.lower()}@example.invalid",
                proposals=[
                    dict(
                        rank=rank,
                        proposal_id=pid,
                        booth_id=bid,
                        category=category,
                        name=names[bid],
                        description=(
                            "Synthetic PTA safety approval for rehearsal only; soft-tip darts and adult supervision."
                            if bid == "G03"
                            else "Fictional rehearsal proposal; live safety, allergen and preparation review still required."
                        ),
                    )
                    for owner, rank, pid, bid, category in proposals
                    if owner == cid
                ],
            )
            for cid, display in CLASSES
        ],
    }
    intake["config"] = dict(
        event_id=event_id,
        game_target=9,
        food_target=13,
        admins=["alex@example.invalid", "robin@example.invalid"],
        initial_deadline="2026-11-01T18:00:00Z",
        grace_hours=48,
        exception_approvers=["alex@example.invalid"],
        publication_approvers=["alex@example.invalid"],
    )
    intake["submissions"] = [
        dict(
            class_id=record["class_id"],
            email=record["contact_email"],
            name=record["contact_name"],
            proposals=[
                dict(
                    name=p["name"], description=p["description"], category=p["category"]
                )
                for p in record["proposals"]
            ],
        )
        for record in intake["classes"]
    ]
    intake["review_decisions"] = {
        record["class_id"]: [
            dict(
                status="APPROVED",
                reason="Synthetic rehearsal approval only",
                booth_id=p["booth_id"],
                name=p["name"],
                category=p["category"],
            )
            for p in record["proposals"]
        ]
        for record in intake["classes"]
    }
    result["google-intake.json"] = (
        json.dumps(intake, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return result


def generate(destination, event_id=DEFAULT_EVENT, force=False):
    if (
        not event_id.strip()
        or event_id != event_id.strip()
        or event_id.startswith(("=", "+", "-", "@"))
        or any(ord(ch) < 32 for ch in event_id)
    ):
        raise ValueError("event_id must be a nonempty spreadsheet-safe identifier")
    root = Path(destination)
    files = generated_files(event_id)
    for name in files:
        path = root / name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("Refusing to write through symbolic links")
    # Check all conflicts before writing anything, including unrelated files.
    # README is maintained separately and never overwritten by this generator.
    if root.exists():
        unexpected = [
            p
            for p in root.rglob("*")
            if p.is_file()
            and p.relative_to(root).as_posix() not in files
            and p.relative_to(root).as_posix() != "README.md"
        ]
        conflicts = [
            root / name
            for name, data in files.items()
            if (root / name).exists()
            and ((root / name).is_symlink() or (root / name).read_bytes() != data)
        ]
        if (unexpected or conflicts) and not force:
            raise ValueError(
                "Destination contains different or unrecognized files; choose an empty directory or explicitly use --force."
            )
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("sample-data"))
    parser.add_argument("--event-id", default=DEFAULT_EVENT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace generated files that differ; unrelated files are retained.",
    )
    args = parser.parse_args()
    try:
        generate(args.output, args.event_id, args.force)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
