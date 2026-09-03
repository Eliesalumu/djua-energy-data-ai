from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


VALID_SCHEMA_VERSION = "1.0"
STALE_TELEMETRY_SECONDS = 3600


class CustomerDecisionIdentity(BaseModel):
    client_id: str | None = None
    kit_id: str | None = None
    device_id: str | None = None
    installation_id: str | None = None
    contract_id: str | None = None
    assignment_id: str | None = None
    resolution_status: str | None = None


class CustomerDecisionContext(BaseModel):
    schema_version: str = Field(..., description="Version du contrat Backend -> IA.")
    request_id: str = Field(..., description="Identifiant de correlation fourni par le backend.")
    as_of: str = Field(..., description="Instant du snapshot de decision.")
    identity: CustomerDecisionIdentity
    telemetry: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    payment: dict[str, Any] = Field(default_factory=dict)
    customer: dict[str, Any] = Field(default_factory=dict)
    contract: dict[str, Any] = Field(default_factory=dict)
    kit_intelligence: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != VALID_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {value}")
        return value


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def _risk_level(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return datetime.fromtimestamp(float(raw), tz=UTC)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _number(payload: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = payload.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _bool(payload: dict[str, Any], name: str) -> bool:
    return bool(payload.get(name, False))


class CustomerDecisionEngine:
    """Rule-based MVP engine that composes customer, payment and kit intelligence."""

    model_version = "customer-decision-rule-mvp-v1"

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Compose les signaux deja prepares: identite, paiement, client, contrat et kit_intelligence.
        try:
            decision_context = CustomerDecisionContext.model_validate(payload)
        except ValidationError as exc:
            return self._invalid_payload_result(payload, exc)

        warnings: list[str] = []
        missing_features: list[str] = []
        identity_status = self._identity_status(decision_context, warnings, missing_features)
        data_quality = self._data_quality(decision_context, warnings, missing_features, identity_status)

        client_value = self._client_value_score(decision_context, warnings)
        payment_risk = self._payment_risk_score(decision_context, warnings, missing_features)
        operational_risk = self._operational_risk_score(decision_context, warnings, missing_features)
        # La priorite finale combine valeur client, risque paiement, risque kit et qualite des donnees.
        data_quality["status"] = self._quality_status_after_scoring(identity_status, warnings, missing_features)
        intervention_priority = self._intervention_priority_score(
            client_value=client_value,
            payment_risk=payment_risk,
            operational_risk=operational_risk,
            identity_status=identity_status,
            data_quality_status=data_quality["status"],
        )

        reasons = self._reasons(decision_context, client_value, payment_risk, operational_risk, data_quality)
        action = self._recommended_action(payment_risk, operational_risk, identity_status, data_quality["status"])
        priority = _risk_level(intervention_priority)
        confidence = self._confidence(data_quality["status"], identity_status, warnings, missing_features)

        identity = decision_context.identity.model_dump()
        reason_codes = self._reason_codes(decision_context, reasons, identity_status, data_quality)
        return {
            "schema_version": "customer-decision-result.v1",
            "decision_id": f"customer-decision-{decision_context.request_id}",
            "request_id": decision_context.request_id,
            "as_of": decision_context.as_of,
            "identity": identity,
            "identity_status": identity_status,
            "scores": {
                "client_value": client_value,
                "payment_risk": payment_risk,
                "operational_risk": operational_risk,
                "intervention_priority": intervention_priority,
            },
            "decision": {
                "priority": priority,
                "recommended_action": action,
                "human_review_required": priority in {"critical", "high"} or confidence < 0.7,
            },
            "reasons": reasons,
            "reason_codes": reason_codes,
            "confidence": confidence,
            "data_quality": {
                "status": data_quality["status"],
                "telemetry_age_seconds": data_quality["telemetry_age_seconds"],
                "missing_features": sorted(set(missing_features)),
                "warnings": warnings,
            },
            "model": {
                "name": "customer_decision_engine",
                "version": self.model_version,
                "type": "rule_based_composition",
                "trained_on_synthetic_data": False,
            },
            "traceability": {
                "assignment_id": identity.get("assignment_id"),
                "model_versions": decision_context.kit_intelligence.get("model_versions", {}),
                "source_prediction_ids": decision_context.kit_intelligence.get("source_prediction_ids", []),
                "decision_engine_version": self.model_version,
            },
        }

    def _invalid_payload_result(self, payload: dict[str, Any], exc: ValidationError) -> dict[str, Any]:
        return {
            "schema_version": "customer-decision-result.v1",
            "request_id": payload.get("request_id"),
            "identity_status": "invalid",
            "scores": {
                "client_value": None,
                "payment_risk": None,
                "operational_risk": None,
                "intervention_priority": None,
            },
            "decision": {
                "priority": "low",
                "recommended_action": "fix_payload",
                "human_review_required": True,
            },
            "reasons": ["invalid_payload"],
            "confidence": 0.0,
            "data_quality": {
                "status": "blocked",
                "telemetry_age_seconds": None,
                "missing_features": [],
                "warnings": [error["msg"] for error in exc.errors()],
            },
            "model": {
                "name": "customer_decision_engine",
                "version": self.model_version,
                "type": "rule_based_composition",
                "trained_on_synthetic_data": False,
            },
        }

    def _identity_status(
        self,
        context: CustomerDecisionContext,
        warnings: list[str],
        missing_features: list[str],
    ) -> str:
        identity = context.identity
        if not identity.resolution_status:
            missing_features.append("identity.resolution_status")
            warnings.append("Statut de resolution identite manquant: le backend doit fournir resolution_status.")
            return "unresolved"
        if identity.resolution_status in {"unresolved", "ambiguous", "conflict", "stale", "partial"}:
            missing_features.append("identity.resolution_status")
            warnings.append(f"Resolution identite non fiable: {identity.resolution_status}.")
            return identity.resolution_status
        if not identity.kit_id or not identity.device_id:
            missing_features.append("identity.kit_id_or_device_id")
            warnings.append("Identite kit/device incomplete: decision client bloquee.")
            return "unresolved"
        if not identity.client_id:
            missing_features.append("identity.client_id")
            warnings.append("Aucun client rattache au kit: le backend doit resoudre l'affectation.")
            return "kit_without_customer"
        if not identity.contract_id or not identity.assignment_id:
            missing_features.append("identity.contract_id_or_assignment_id")
            warnings.append("Affectation client-kit incomplete: confiance reduite.")
            return "partial"
        if context.data_quality.get("identity_resolved") is False:
            warnings.append("Le backend signale une identite non resolue.")
            return "unresolved"
        return "resolved"

    def _data_quality(
        self,
        context: CustomerDecisionContext,
        warnings: list[str],
        missing_features: list[str],
        identity_status: str,
    ) -> dict[str, Any]:
        missing_from_backend = context.data_quality.get("missing_features") or []
        for feature in missing_from_backend:
            missing_features.append(str(feature))
        for warning in context.data_quality.get("warnings") or []:
            warnings.append(str(warning))

        as_of = _parse_datetime(context.as_of) or datetime.now(tz=UTC)
        event_time = _parse_datetime(context.telemetry.get("event_time"))
        telemetry_age_seconds = context.data_quality.get("telemetry_age_seconds")
        if telemetry_age_seconds is None and event_time:
            telemetry_age_seconds = max(0, int((as_of - event_time).total_seconds()))

        if telemetry_age_seconds is None:
            missing_features.append("data_quality.telemetry_age_seconds")
            warnings.append("Age de telemetrie indisponible: fraicheur non garantie.")
        else:
            telemetry_age_seconds = int(telemetry_age_seconds)
            if telemetry_age_seconds > STALE_TELEMETRY_SECONDS:
                warnings.append("Telemetrie obsolete: risque operationnel calcule avec confiance reduite.")

        if identity_status in {"unresolved", "kit_without_customer", "ambiguous", "conflict", "stale"}:
            status = "blocked"
        elif missing_features or warnings:
            status = "partial"
        else:
            status = "complete"
        return {"status": status, "telemetry_age_seconds": telemetry_age_seconds}

    def _quality_status_after_scoring(
        self,
        identity_status: str,
        warnings: list[str],
        missing_features: list[str],
    ) -> str:
        if identity_status in {"unresolved", "kit_without_customer", "ambiguous", "conflict", "stale"}:
            return "blocked"
        if warnings or missing_features:
            return "partial"
        return "complete"

    def _client_value_score(self, context: CustomerDecisionContext, warnings: list[str]) -> int:
        customer = context.customer
        contract = context.contract
        tenure = _number(customer, "tenure_months", "customer_tenure_months") or 0.0
        active_contracts = _number(customer, "active_contracts") or 1.0
        periodic_amount = _number(contract, "periodic_amount_usd", "periodicAmountUSD", "monthly_fee_usd") or 0.0
        segment = str(customer.get("customer_segment") or "").lower()

        score = 20
        score += min(30, tenure * 1.2)
        score += min(20, max(0, active_contracts - 1) * 10)
        score += min(25, periodic_amount * 1.0)
        if segment in {"business", "enterprise", "priority"}:
            score += 20
        elif segment in {"residential", "household"}:
            score += 8
        elif segment:
            score += 5
        else:
            warnings.append("Segment client absent: valeur client estimee prudemment.")
        return _clamp_score(score)

    def _payment_risk_score(
        self,
        context: CustomerDecisionContext,
        warnings: list[str],
        missing_features: list[str],
    ) -> int:
        # Ici on consomme des features paiement calculees cote Data, pas les paiements bruts.
        payment = context.payment
        if not payment:
            missing_features.append("payment")
            warnings.append("Donnees paiement absentes: Payment Risk non fiable.")
            return 50

        late_count = _number(payment, "late_payments_last_6_months", "late_payment_count_12m") or 0.0
        missed_count = _number(payment, "missed_payments_last_6_months", "missed_payment_count_12m") or 0.0
        failed_count = _number(payment, "failed_payments_last_6_months", "failed_payment_count_12m") or 0.0
        average_days_late = _number(payment, "average_days_late") or 0.0
        outstanding_balance = _number(payment, "outstanding_balance", "amount_due") or 0.0
        success_rate = _number(payment, "payment_success_rate")
        days_since_last_payment = _number(payment, "days_since_last_payment")
        last_payment_status = str(payment.get("last_payment_status") or "").lower()

        score = 10
        score += late_count * 8
        score += missed_count * 18
        score += failed_count * 12
        score += min(20, average_days_late * 1.5)
        score += min(25, outstanding_balance * 1.5)
        if success_rate is not None:
            score += max(0, (0.85 - success_rate) * 60)
        if days_since_last_payment is not None and days_since_last_payment > 30:
            score += min(25, (days_since_last_payment - 30) * 0.5)
        if last_payment_status in {"missed", "failed", "rejected", "late", "pending"}:
            score += 12
        return _clamp_score(score)

    def _operational_risk_score(
        self,
        context: CustomerDecisionContext,
        warnings: list[str],
        missing_features: list[str],
    ) -> int:
        kit = context.kit_intelligence
        telemetry = context.telemetry
        if not kit and not telemetry:
            missing_features.append("kit_intelligence")
            warnings.append("Aucune intelligence kit ni telemetrie: risque operationnel inconnu.")
            return 50

        operational_score = None
        if isinstance(kit.get("operational_risk"), dict):
            operational_score = _number(kit["operational_risk"], "score")
        if operational_score is not None:
            score = operational_score
        else:
            maintenance_payload = kit.get("maintenance") if isinstance(kit.get("maintenance"), dict) else {}
            security_payload = kit.get("security") if isinstance(kit.get("security"), dict) else {}
            maintenance_risk = _number(kit, "maintenance_risk", "maintenance_risk_score", "maintenance_probability")
            security_risk = _number(kit, "security_risk", "security_risk_score", "security_probability")
            maintenance_risk = maintenance_risk if maintenance_risk is not None else _number(maintenance_payload, "risk_probability")
            security_risk = security_risk if security_risk is not None else _number(security_payload, "risk_probability")
            if maintenance_risk is not None and maintenance_risk <= 1:
                maintenance_risk *= 100
            if security_risk is not None and security_risk <= 1:
                security_risk *= 100

            risk_candidates = [value for value in [maintenance_risk, security_risk] if value is not None]
            score = max(risk_candidates) if risk_candidates else 25.0
        if _bool(kit, "critical_anomaly"):
            score = max(score, 90)
        if str(kit.get("battery_health") or "").lower() in {"degraded", "critical"}:
            score = max(score, 70)

        state_of_health = _number(telemetry, "state_of_health_pct")
        state_of_charge = _number(telemetry, "state_of_charge_pct")
        if state_of_health is not None and state_of_health < 80:
            score = max(score, 70 + (80 - state_of_health) * 0.8)
        if state_of_charge is not None and state_of_charge < 25:
            score = max(score, 65)
        if telemetry.get("connection_status") == "disconnected":
            score = max(score, 70)
        return _clamp_score(score)

    def _intervention_priority_score(
        self,
        *,
        client_value: int,
        payment_risk: int,
        operational_risk: int,
        identity_status: str,
        data_quality_status: str,
    ) -> int:
        if identity_status in {"unresolved", "kit_without_customer", "ambiguous", "conflict", "stale"}:
            return 0
        if operational_risk >= 70:
            score = operational_risk * 0.75 + client_value * 0.2 + max(0, 40 - payment_risk) * 0.05
        elif payment_risk >= 70:
            score = payment_risk * 0.55 + client_value * 0.15 + operational_risk * 0.1
        else:
            score = operational_risk * 0.5 + payment_risk * 0.25 + client_value * 0.25
        if data_quality_status == "partial":
            score *= 0.9
        return _clamp_score(score)

    def _recommended_action(
        self,
        payment_risk: int,
        operational_risk: int,
        identity_status: str,
        data_quality_status: str,
    ) -> str:
        if identity_status in {"unresolved", "kit_without_customer", "ambiguous", "conflict", "stale"}:
            return "resolve_identity"
        if data_quality_status == "blocked":
            return "fix_data_quality"
        if operational_risk >= 85:
            return "urgent_technical_intervention"
        if operational_risk >= 70:
            return "technical_intervention"
        if payment_risk >= 70:
            return "commercial_follow_up"
        if payment_risk >= 50:
            return "payment_monitoring"
        return "monitor"

    def _reasons(
        self,
        context: CustomerDecisionContext,
        client_value: int,
        payment_risk: int,
        operational_risk: int,
        data_quality: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        telemetry = context.telemetry
        kit = context.kit_intelligence
        if operational_risk >= 85:
            reasons.append("operational_risk_critical")
        elif operational_risk >= 70:
            reasons.append("operational_risk_high")
        if _number(telemetry, "state_of_health_pct") is not None and float(telemetry["state_of_health_pct"]) < 80:
            reasons.append("state_of_health_degraded")
        if _bool(kit, "critical_anomaly"):
            reasons.append("critical_anomaly")
        if payment_risk >= 70:
            reasons.append("payment_risk_high")
        elif payment_risk < 35:
            reasons.append("customer_payment_behavior_good")
        if client_value >= 75:
            reasons.append("client_value_high")
        if data_quality["status"] != "complete":
            reasons.append("data_quality_not_complete")
        return reasons or ["no_major_risk_signal"]

    def _reason_codes(
        self,
        context: CustomerDecisionContext,
        reasons: list[str],
        identity_status: str,
        data_quality: dict[str, Any],
    ) -> list[str]:
        mapped = {
            "operational_risk_critical": "HIGH_OPERATIONAL_RISK",
            "operational_risk_high": "HIGH_OPERATIONAL_RISK",
            "state_of_health_degraded": "LOW_STATE_OF_HEALTH",
            "critical_anomaly": "CRITICAL_KIT_ANOMALY",
            "payment_risk_high": "PAYMENT_RISK_HIGH",
            "client_value_high": "HIGH_CLIENT_VALUE",
            "data_quality_not_complete": "DATA_INCOMPLETE",
        }
        codes = [mapped[item] for item in reasons if item in mapped]
        codes.extend(str(item) for item in context.kit_intelligence.get("reason_codes", []))
        if identity_status in {"unresolved", "kit_without_customer"}:
            codes.append("IDENTITY_UNRESOLVED")
        elif identity_status == "ambiguous":
            codes.append("IDENTITY_AMBIGUOUS")
        elif identity_status == "conflict":
            codes.append("IDENTITY_CONFLICT")
        elif identity_status == "stale":
            codes.append("IDENTITY_STALE")
        if data_quality["status"] == "partial":
            codes.append("DATA_INCOMPLETE")
        if data_quality["status"] == "blocked":
            codes.append("DATA_BLOCKED")
        return sorted(set(codes)) or ["NO_MAJOR_RISK_SIGNAL"]

    def _confidence(
        self,
        data_quality_status: str,
        identity_status: str,
        warnings: list[str],
        missing_features: list[str],
    ) -> float:
        if identity_status in {"unresolved", "kit_without_customer", "ambiguous", "conflict", "stale"}:
            return 0.0
        confidence = 0.9
        if identity_status == "partial":
            confidence -= 0.18
        if data_quality_status == "partial":
            confidence -= 0.12
        confidence -= min(0.3, 0.04 * len(set(missing_features)))
        confidence -= min(0.2, 0.02 * len(warnings))
        return round(max(0.0, min(1.0, confidence)), 2)
