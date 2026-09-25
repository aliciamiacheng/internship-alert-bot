"""Fail the workflow if a configured source was not actually checked successfully."""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent


def verify():
    with (ROOT / "companies.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    report = json.loads((ROOT / "source_health.json").read_text())
    checked = datetime.fromisoformat(report["checked_at_utc"])
    problems = []
    if (datetime.now(timezone.utc) - checked).total_seconds() > 7200:
        problems.append("Health report is more than two hours old")
    names = [row["company"] for row in rows]
    if len(set(names)) != len(names):
        problems.append("Duplicate company names in companies.csv")
    statuses = {item["company"]: item for item in report["companies"]}
    if len(statuses) != len(rows):
        problems.append("Missing or duplicate company verification rows")
    active = 0
    for row in rows:
        item = statuses.get(row["company"])
        if not item:
            problems.append(f"{row['company']}: no verification result")
        elif row["source_type"]:
            active += 1
            if item["status"] != "ok":
                problems.append(f"{row['company']}: {item['status']} — {item['detail']}")
        elif item["status"] != "unconfigured":
            problems.append(f"{row['company']}: unexpected monitored status")
    print(f"Verified {active}/{len(rows)} configured sources; {len(rows)-active} remain unconfigured.")
    for problem in problems:
        print("VERIFICATION FAILED:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(verify())
