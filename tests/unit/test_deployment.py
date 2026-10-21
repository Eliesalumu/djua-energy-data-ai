import asyncio
import json
import os
import subprocess
import sys
from urllib.error import HTTPError

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import apps.api.main as main
from djua_energy.chat import service as chat_module
from djua_energy.chat.service import DjuaChatService, OpenAIResponsesClient
from djua_energy.config.http import cors_origins
from djua_energy.config.runtime import PROJECT_ROOT
from djua_energy.database.realtime_store import RealtimeTelemetryStore


def request(app, path, method="GET", body=None, headers=()):
    async def run():
        output = []
        async def receive():
            return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b"", "more_body": False}
        async def send(message):
            output.append(message)
        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "scheme": "http", "method": method,
                   "path": path, "raw_path": path.encode(), "query_string": b"", "headers": list(headers) + ([(b"content-type", b"application/json")] if body is not None else []),
                   "client": ("127.0.0.1", 1), "server": ("test", 80), "root_path": ""}, receive, send)
        start = next(item for item in output if item["type"] == "http.response.start")
        raw = b"".join(item.get("body", b"") for item in output if item["type"] == "http.response.body")
        return start["status"], dict(start["headers"]), raw
    return asyncio.run(run())


@pytest.fixture(scope="module")
def dataset():
    return pd.read_csv(PROJECT_ROOT / "data/generated/mvp_dataset.csv")


def test_health_is_json_and_does_not_touch_dependencies(monkeypatch):
    class Broken:
        def __getattr__(self, name):
            raise AssertionError("Liveness accessed a dependency")
    monkeypatch.setattr(main, "engine", Broken())
    monkeypatch.setattr(main, "realtime_store", Broken())
    monkeypatch.setattr(main, "chat_service", Broken())
    status, headers, body = request(main.app, "/health")
    assert status == 200
    assert b"application/json" in headers[b"content-type"]
    assert json.loads(body)["status"] == "ok"


def test_import_and_health_work_without_models_dataset_or_database(tmp_path):
    code = """
import joblib, pandas
def fail(*args, **kwargs):
    raise AssertionError('Heavy dependency used at import')
joblib.load = fail
pandas.read_csv = fail
from apps.api.main import health, engine, realtime_store
assert health()['status'] == 'ok'
assert engine._instance is None
assert realtime_store._instance is None
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(PROJECT_ROOT), str(PROJECT_ROOT / "src")]),
               DJUA_CHAT_DATASET=str(tmp_path / "missing.csv"), DJUA_DATABASE_URL="invalid-storage-url")
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_static_page_and_dataset_do_not_depend_on_cwd(monkeypatch, tmp_path):
    from djua_energy.chat.context_builder import load_dataset
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DJUA_CHAT_DATASET", raising=False)
    assert not load_dataset().empty
    status, headers, body = request(main.app, "/")
    assert status == 200 and b"text/html" in headers[b"content-type"]


@pytest.mark.parametrize("failure,code", [
    (HTTPError("private", 401, "secret-sentinel", {}, None), "AI_AUTHENTICATION_ERROR"),
    (HTTPError("private", 429, "secret-sentinel", {}, None), "AI_RATE_LIMIT"),
    (HTTPError("private", 500, "secret-sentinel", {}, None), "AI_PROVIDER_ERROR"),
    (HTTPError("private", 502, "secret-sentinel", {}, None), "AI_PROVIDER_ERROR"),
    (HTTPError("private", 503, "secret-sentinel", {}, None), "AI_PROVIDER_ERROR"),
    (TimeoutError("secret-sentinel"), "AI_TIMEOUT"),
    (RuntimeError("secret-sentinel"), "AI_PROVIDER_ERROR"),
])
def test_provider_failure_preserves_valid_local_fallback(monkeypatch, dataset, failure, code, caplog):
    class Provider:
        available = True
        def generate(self, message, context):
            raise failure
    monkeypatch.setattr(main, "chat_service", DjuaChatService(dataset=dataset, engine=object(), llm_client=Provider()))
    status, _, raw = request(main.app, "/ai/chat", "POST", {"message": "Comment va le parc ?"})
    body = json.loads(raw)
    assert status == 200 and body["ok"] is True and body["used_llm"] is False
    assert body["answer"] and body["warning"]["code"] == code
    assert "secret-sentinel" not in raw.decode() + caplog.text


def test_missing_key_is_reported_as_fallback_not_401(monkeypatch, dataset):
    monkeypatch.setattr(chat_module, "_configured_api_key", lambda: None)
    monkeypatch.setattr(main, "chat_service", DjuaChatService(dataset=dataset, engine=object(), llm_client=OpenAIResponsesClient()))
    status, _, body = request(main.app, "/ai/chat", "POST", {"message": "Etat du parc"})
    assert status == 200
    assert json.loads(body)["warning"]["code"] == "AI_NOT_CONFIGURED"


def test_missing_dataset_returns_structured_error_and_health_survives(monkeypatch, tmp_path):
    monkeypatch.setenv("DJUA_CHAT_DATASET", str(tmp_path / "missing.csv"))
    monkeypatch.setattr(main, "chat_service", DjuaChatService(engine=object()))
    status, _, body = request(main.app, "/ai/chat", "POST", {"message": "Etat du parc"})
    assert status == 503 and json.loads(body)["error"]["code"] == "CHAT_CONTEXT_UNAVAILABLE"
    assert request(main.app, "/health")[0] == 200


@pytest.mark.parametrize("payload", [{}, {"message": 123}, {"message": ""}, {"message": "   "}, {"message": "x" * 4001}])
def test_invalid_request_is_rejected_without_chat_call(monkeypatch, payload):
    class NoCalls:
        def answer(self, message):
            raise AssertionError("Invalid request reached chat")
    monkeypatch.setattr(main, "chat_service", NoCalls())
    assert request(main.app, "/ai/chat", "POST", payload)[0] == 422


def test_cors_preflight_for_configured_frontend_and_denial(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://frontend-example.onrender.com")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_credentials=True, allow_methods=["POST"], allow_headers=["*"])
    headers = [(b"origin", b"https://frontend-example.onrender.com"), (b"access-control-request-method", b"POST"), (b"access-control-request-headers", b"content-type,authorization")]
    status, result, _ = request(app, "/ai/chat", "OPTIONS", headers=headers)
    assert status == 200 and result[b"access-control-allow-origin"] == headers[0][1]
    assert request(app, "/ai/chat", "OPTIONS", headers=[(b"origin", b"https://foreign.example"), headers[1]])[0] == 400


def test_main_app_has_cors_middleware():
    assert any(middleware.cls is CORSMiddleware for middleware in main.app.user_middleware)


@pytest.mark.parametrize("origin", ["*", "https://frontend.example/path", "https://user:password@frontend.example"])
def test_invalid_cors_configuration_fails_explicitly(monkeypatch, origin):
    monkeypatch.setenv("CORS_ORIGINS", origin)
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        cors_origins()


def test_ready_reports_missing_dataset_without_provider_call(monkeypatch, tmp_path):
    monkeypatch.setenv("DJUA_CHAT_DATASET", str(tmp_path / "missing.csv"))
    monkeypatch.setattr(main, "realtime_store", RealtimeTelemetryStore(tmp_path / "new.sqlite"))
    status, _, raw = request(main.app, "/ready")
    assert status == 503 and json.loads(raw)["checks"]["dataset"] is False
