from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.contracts import validate_payload
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService

app = FastAPI(title="Djua Energy IoT Demo", version="0.1.0")
engine = LocalInferenceEngine("artifacts")
telemetry_service = TelemetryIngestionService(engine)


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


@app.post("/telemetry/analyze")
def telemetry_analyze(payload: TelemetryWindowRequest) -> dict:
    if not payload.records:
        raise HTTPException(status_code=400, detail="records cannot be empty")
    try:
        return telemetry_service.process_window(payload.records)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/telemetry/metrics")
def telemetry_metrics() -> dict:
    return telemetry_service.metrics.snapshot()


@app.get("/telemetry/quarantine")
def telemetry_quarantine() -> dict:
    return {"entries": [entry.__dict__ for entry in telemetry_service.quarantine_store.list_entries()]}


@app.get("/telemetry/audit")
def telemetry_audit() -> dict:
    return {"events": [event.__dict__ for event in telemetry_service.audit_log.list_events()]}


@app.post("/demo/generate")
def demo_generate() -> dict:
    generator = SyntheticTelemetryGenerator(seed=11, num_kits=2)
    records = generator.generate(scenarios=["normal_operation", "suspicious_movement"], duration_hours=2)
    return {"records": records[:3]}
