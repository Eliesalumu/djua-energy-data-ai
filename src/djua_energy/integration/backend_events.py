from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class BackendEventsError(RuntimeError):
    """Erreur d'integration entre le backend metier et l'API IA/Data."""


class BackendResolvedEventsClient:
    """Client pull: lit les snapshots resolus exposes par le backend metier et envoie les ACK."""

    def __init__(
        self,
        base_url: str,
        *,
        resolved_events_path: str = "/v1/ai/resolved-telemetry-events",
        ack_path_template: str = "/v1/ai/resolved-telemetry-events/{request_id}/ack",
        timeout_seconds: float = 15.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self.base_url = base_url.rstrip("/")
        self.resolved_events_path = resolved_events_path
        self.ack_path_template = ack_path_template
        self.timeout_seconds = timeout_seconds

    def fetch_resolved_events(self, *, cursor: str | None = None, limit: int = 100) -> dict[str, Any]:
        query = {"limit": limit}
        if cursor:
            query["cursor"] = cursor
        url = f"{self.base_url}{self.resolved_events_path}?{urlencode(query)}"
        return self._request_json("GET", url)

    def ack_event(self, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.ack_path_template.format(request_id=request_id)
        url = f"{self.base_url}{path}"
        return self._request_json("POST", url, payload)

    def process_resolved_events(
        self,
        *,
        processor: Callable[[dict[str, Any]], dict[str, Any]],
        cursor: str | None = None,
        limit: int = 100,
        ack: bool = True,
    ) -> dict[str, Any]:
        page = self.fetch_resolved_events(cursor=cursor, limit=limit)
        items = page.get("items") or []
        processed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for item in items:
            request_id = str(item.get("request_id") or "")
            try:
                result = processor(item)
                ack_payload = _processed_ack_payload(result)
                ack_response = self.ack_event(request_id, ack_payload) if ack and request_id else None
                processed.append(
                    {
                        "request_id": request_id,
                        "decision_id": (result.get("persistence") or {}).get("decision_id"),
                        "prediction_id": (result.get("trend_source") or {}).get("stored_prediction_id"),
                        "ack_sent": bool(ack_response is not None),
                        "ack_response": ack_response,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - batch sync must report item-level failures.
                error_payload = _failed_ack_payload(str(exc))
                ack_response = None
                if ack and request_id:
                    try:
                        ack_response = self.ack_event(request_id, error_payload)
                    except Exception as ack_exc:  # noqa: BLE001 - keep original processing error visible.
                        error_payload["ack_error"] = str(ack_exc)
                failed.append(
                    {
                        "request_id": request_id,
                        "error": str(exc),
                        "ack_sent": bool(ack_response is not None),
                        "ack_response": ack_response,
                    }
                )

        return {
            "status": "completed_with_errors" if failed else "completed",
            "source": {
                "base_url": self.base_url,
                "resolved_events_path": self.resolved_events_path,
                "ack_path_template": self.ack_path_template,
                "cursor": cursor,
                "limit": limit,
            },
            "received": len(items),
            "processed_count": len(processed),
            "failed_count": len(failed),
            "next_cursor": page.get("next_cursor"),
            "processed": processed,
            "failed": failed,
        }

    def _request_json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BackendEventsError(f"Backend returned HTTP {exc.code} for {url}: {detail}") from exc
        except URLError as exc:
            raise BackendEventsError(f"Cannot reach backend at {url}: {exc.reason}") from exc
        if not body:
            return {}
        return json.loads(body)


def _processed_ack_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "processed",
        "processed_at": datetime.now(UTC).isoformat(),
    }


def _failed_ack_payload(error: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "processed_at": datetime.now(UTC).isoformat(),
        "error": error,
    }
