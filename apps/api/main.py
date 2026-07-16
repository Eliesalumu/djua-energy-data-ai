from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.contracts import validate_payload

app = FastAPI(title="Djua Energy IoT Demo", version="0.1.0")
engine = LocalInferenceEngine("artifacts")


class TelemetryWindowRequest(BaseModel):
    records: list[dict] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "djua-energy-iot-demo"}


@app.post("/maintenance/predict")
def maintenance_predict(payload: TelemetryWindowRequest) -> dict:
    if not payload.records:
        raise HTTPException(status_code=400, detail="records cannot be empty")
    for record in payload.records:
        validation = validate_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)
    return engine.infer_maintenance(payload.records)


@app.post("/security/predict")
def security_predict(payload: TelemetryWindowRequest) -> dict:
    if not payload.records:
        raise HTTPException(status_code=400, detail="records cannot be empty")
    for record in payload.records:
        validation = validate_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)
    return engine.infer_security(payload.records)


@app.post("/demo/generate")
def demo_generate() -> dict:
    generator = SyntheticTelemetryGenerator(seed=11, num_kits=2)
    records = generator.generate(scenarios=["normal_operation", "suspicious_movement"], duration_hours=2)
    return {"records": records[:3]}
