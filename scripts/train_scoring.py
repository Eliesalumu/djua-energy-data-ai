from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from djua_energy.scoring.model import train_customer_scoring_model


if __name__ == "__main__":
    metadata = train_customer_scoring_model()
    print(json.dumps(metadata, indent=2))
