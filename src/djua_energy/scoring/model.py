from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from djua_energy.features.customer_features import CUSTOMER_SCORING_FEATURES
from djua_energy.scoring.dataset import generate_historical_customer_dataset


ARTIFACT_DIR = Path("artifacts")


def risk_level_from_probability(probability: float) -> str:
    if probability >= 0.65:
        return "high"
    if probability >= 0.35:
        return "medium"
    return "low"


def score_from_probability(probability: float) -> int:
    return max(0, min(100, round((1 - probability) * 100)))


def train_customer_scoring_model(
    output_dir: str | Path | None = None,
    dataset_path: str | Path = "data/generated/customer_scoring_history.csv",
    num_clients: int = 500,
    months_per_client: int = 12,
) -> dict[str, Any]:
    output_dir = Path(output_dir or ARTIFACT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = generate_historical_customer_dataset(
        output_path=dataset_path,
        num_clients=num_clients,
        months_per_client=months_per_client,
    )
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=7)
    train_idx, test_idx = next(splitter.split(dataset, dataset["default_next_90d"], groups=dataset["client_id"]))

    train_df = dataset.iloc[train_idx]
    test_df = dataset.iloc[test_idx]
    model = RandomForestClassifier(
        n_estimators=120,
        max_depth=8,
        min_samples_leaf=8,
        class_weight="balanced",
        random_state=7,
    )
    model.fit(train_df[CUSTOMER_SCORING_FEATURES], train_df["default_next_90d"])

    probabilities = model.predict_proba(test_df[CUSTOMER_SCORING_FEATURES])[:, 1]
    predictions = model.predict(test_df[CUSTOMER_SCORING_FEATURES])
    metrics = {
        "accuracy": round(float(accuracy_score(test_df["default_next_90d"], predictions)), 4),
        "precision": round(float(precision_score(test_df["default_next_90d"], predictions, zero_division=0)), 4),
        "recall": round(float(recall_score(test_df["default_next_90d"], predictions, zero_division=0)), 4),
        "f1": round(float(f1_score(test_df["default_next_90d"], predictions, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(test_df["default_next_90d"], probabilities)), 4),
    }

    joblib.dump(model, output_dir / "customer_scoring_model.joblib")
    joblib.dump(CUSTOMER_SCORING_FEATURES, output_dir / "customer_scoring_features.joblib")

    metadata = {
        "model_version": "customer-scoring-synthetic-v1",
        "problem": "classification_binaire_default_90d",
        "target": "default_next_90d",
        "features": CUSTOMER_SCORING_FEATURES,
        "training_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "clients": int(dataset["client_id"].nunique()),
        "history_rows": int(len(dataset)),
        "positive_rate": round(float(dataset["default_next_90d"].mean()), 4),
        "metrics": metrics,
        "synthetic_data": True,
        "limitations": [
            "Modele entraine sur donnees synthetiques, a remplacer progressivement par des historiques reels.",
            "Decision finale a valider par une revue humaine pour les cas limites ou sensibles.",
        ],
    }
    (output_dir / "customer_scoring_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


class CustomerScoringModel:
    def __init__(self, artifact_dir: str | Path | None = None):
        self.artifact_dir = Path(artifact_dir or ARTIFACT_DIR)
        self.model = joblib.load(self.artifact_dir / "customer_scoring_model.joblib")
        self.features = joblib.load(self.artifact_dir / "customer_scoring_features.joblib")
        self.metadata = json.loads((self.artifact_dir / "customer_scoring_metadata.json").read_text(encoding="utf-8"))

    def predict(self, features: pd.DataFrame) -> dict[str, Any]:
        probability = float(self.model.predict_proba(features[self.features])[:, 1][0])
        return {
            "default_probability_90d": round(probability, 3),
            "score": score_from_probability(probability),
            "risk_level": risk_level_from_probability(probability),
            "model_version": self.metadata["model_version"],
            "features": features.iloc[0].to_dict(),
        }
