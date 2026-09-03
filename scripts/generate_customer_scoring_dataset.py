from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from djua_energy.scoring.dataset import generate_historical_customer_dataset


if __name__ == "__main__":
    dataset = generate_historical_customer_dataset()
    print(
        f"Dataset genere: {len(dataset)} lignes, "
        f"{dataset['client_id'].nunique()} clients, "
        f"taux defaut 90j={dataset['default_next_90d'].mean():.3f}"
    )
