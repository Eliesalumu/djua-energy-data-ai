from pathlib import Path

from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.train import train_models
from djua_energy.pipeline.inference import LocalInferenceEngine


def main() -> None:
    generator = SyntheticTelemetryGenerator(seed=11, num_kits=2)
    records = generator.generate(scenarios=["normal_operation", "suspicious_movement"], duration_hours=2)
    print("Generated records:", len(records))
    train_models("artifacts")
    engine = LocalInferenceEngine("artifacts")
    result = engine.infer_maintenance(records[:3])
    security_result = engine.infer_security(records[:3])
    print("Maintenance:", result)
    print("Security:", security_result)


if __name__ == "__main__":
    main()
