from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from djua_energy.pipeline.synthetic_data import generate_mvp_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the MVP synthetic telemetry dataset.")
    parser.add_argument("--rows", type=int, default=10000, help="Target number of rows to generate.")
    parser.add_argument("--output", default="data/generated/mvp_dataset.csv", help="CSV output path.")
    args = parser.parse_args()

    dataset = generate_mvp_dataset(output_path=Path(args.output), target_rows=args.rows)
    print(f"Generated {len(dataset)} rows at {args.output}")


if __name__ == "__main__":
    main()
