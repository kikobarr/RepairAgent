#!/usr/bin/env python3
import csv
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
BUGGY_LINES_DIR = ROOT_DIR / "repair_agent" / "defects4j" / "buggy-lines"
PROJECTS_DIR = ROOT_DIR / "repair_agent" / "defects4j" / "framework" / "projects"
FIXED_LIST_PATH = ROOT_DIR / "data" / "final_list_of_fixed_bugs"
OUTPUT_CSV = ROOT_DIR / "analysis" / "fault_localization.csv"


def load_canonical_bugs(projects_dir: Path) -> List[Tuple[str, str]]:
    """Return [(Project, BugID)] for all active bugs across projects."""
    bugs: List[Tuple[str, str]] = []
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        active_csv = project_dir / "active-bugs.csv"
        if not active_csv.exists():
            continue
        with active_csv.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                bug_id = row.get("bug.id")
                if not bug_id:
                    continue
                bugs.append((project_dir.name, bug_id.strip()))
    return bugs


def load_fixed_bugs(path: Path) -> Set[Tuple[str, str]]:
    fixed: Set[Tuple[str, str]] = set()
    if not path.exists():
        return fixed
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            project, bug_id = parts[0], parts[1]
            fixed.add((project, bug_id))
    return fixed


def analyze_bug(project: str, bug_id: str) -> Tuple[int, int, int]:
    """Return localized, fault_of_omission, multi_line flags."""
    file_path = BUGGY_LINES_DIR / f"{project}-{bug_id}.buggy.lines"
    if not file_path.exists():
        return 0, 0, 0

    with file_path.open() as fh:
        entries = [line.strip() for line in fh if line.strip()]

    if not entries:
        return 0, 0, 0

    fault_flag = 1 if any("FAULT_OF_OMISSION" in entry for entry in entries) else 0
    multi_flag = 1 if len(entries) > 1 else 0
    return 1, fault_flag, multi_flag


def write_results(rows: List[Dict[str, int]]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "project",
        "bug_index",
        "localized",
        "fault_of_omission",
        "multi_line",
        "fixed_by_repairagent",
    ]
    with OUTPUT_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    canonical_bugs = load_canonical_bugs(PROJECTS_DIR)
    fixed_bugs = load_fixed_bugs(FIXED_LIST_PATH)

    rows: List[Dict[str, int]] = []
    missing_localization: List[Tuple[str, str]] = []

    for project, bug_id in sorted(canonical_bugs, key=lambda x: (x[0].lower(), int(x[1]))):
        localized, fault_flag, multi_flag = analyze_bug(project, bug_id)
        if not localized:
            missing_localization.append((project, bug_id))
        fixed_flag = 1 if (project, bug_id) in fixed_bugs else 0
        rows.append(
            {
                "project": project,
                "bug_index": bug_id,
                "localized": localized,
                "fault_of_omission": fault_flag,
                "multi_line": multi_flag,
                "fixed_by_repairagent": fixed_flag,
            }
        )

    write_results(rows)

    total = len(canonical_bugs)
    missing = len(missing_localization)
    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV}")
    print(f"Total canonical bugs: {total}")
    print(f"Bugs without buggy-lines localization: {missing}")
    if missing:
        sample = ", ".join(f"{p}-{b}" for p, b in missing_localization[:10])
        print(f"Examples: {sample}")


if __name__ == "__main__":
    main()
