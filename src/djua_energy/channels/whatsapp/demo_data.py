"""Read-only synthetic dataset used for the explicitly configured WhatsApp demo.

No writes, no predictions fabricated, and no grant or role changes.
"""
from collections import defaultdict

import pandas as pd

from djua_energy.pipeline.synthetic_data import dataset_row_to_telemetry_record


class SyntheticDatasetStore:
    context_source = "SyntheticMvpDataset"

    def __init__(self, path):
        self.records = defaultdict(list)
        for _, row in pd.read_csv(path).iterrows():
            record = dataset_row_to_telemetry_record(row)
            record["source"] = "synthetic_mvp_dataset"
            self.records[record["device_id"]].append(record)
        for records in self.records.values():
            records.sort(key=lambda r: int(r["event_time"]))

    def list_observed_device_ids(self):
        return sorted(self.records)

    def get_device_state(self, device_id):
        return None

    def recent_records_for_device(self, device_id, *, limit=24):
        return self.records.get(device_id, [])[-limit:]

    def prediction_history(self, device_id, *, limit=5):
        return []
