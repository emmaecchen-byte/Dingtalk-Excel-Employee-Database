#!/usr/bin/env python3
"""Generate the master attendance Excel template (.xlsx)."""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.excel.template_generator import generate_attendance_template  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate attendance master Excel template")
    parser.add_argument("--year", type=int, default=2026, help="Template year (default: 2026)")
    parser.add_argument("--month", type=int, default=5, help="Template month (default: 5)")
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_ROOT / "templates" / "attendance_master_template.xlsx",
        help="Output .xlsx path",
    )
    args = parser.parse_args()

    path = generate_attendance_template(args.output, args.year, args.month)
    print(f"Template saved: {path}")


if __name__ == "__main__":
    main()
