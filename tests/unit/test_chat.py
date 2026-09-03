import pandas as pd

from djua_energy.chat.context_builder import build_device_context, extract_device_query
from djua_energy.chat.service import DjuaChatService, OpenAIResponsesClient


class _NoLlmClient:
    available = False


def test_extract_device_query_normalizes_device_id() -> None:
    query = extract_device_query("Parle-moi du device 4")

    assert query.device_id == "device-4"
    assert query.intent == "device_diagnosis"


def test_build_device_context_exposes_operational_indicators() -> None:
    df = pd.read_csv("data/generated/mvp_dataset.csv")
    context = build_device_context("device-3", dataset=df)

    assert context["found"] is True
    assert context["device_id"] == "device-3"
    assert context["global_status"] in {"critique", "eleve", "normal"}
    assert context["indicators"]["max_connectivity_gap_seconds"] >= 300
    assert context["indicators"]["enclosure_opened"] is True
    assert context["model_predictions"]


def test_chat_service_fallback_answers_from_context_without_llm() -> None:
    df = pd.read_csv("data/generated/mvp_dataset.csv")
    service = DjuaChatService(dataset=df, llm_client=_NoLlmClient())

    result = service.answer("Parle-moi du device-3")

    assert result.used_llm is False
    assert result.device_id == "device-3"
    assert "device-3" in result.answer
    assert "Action recommandee" in result.answer
    assert result.sources


def test_openai_client_prefers_project_model_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DJUA_OPENAI_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_MODEL", "older-model")

    client = OpenAIResponsesClient()

    assert client.available is True
    assert client.model == "gpt-5-mini"
