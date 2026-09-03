"""API FastAPI DJUA ENERGY.

Les endpoints frontend sont declares dans ce fichier.
Chercher `@app.get("/frontend/command-center")` pour le Command Center.

Routes frontend actuellement disponibles :
- GET /frontend/command-center
- GET /frontend/fleet
- GET /frontend/decisions/{decision_id}
- GET /frontend/kits/{kit_id}/digital-twin
- GET /frontend/interventions/create
- GET /frontend/customers/{client_id}/risk-profile
- GET /frontend/performance
- GET /frontend/admin/data-ai
- GET /frontend/realtime/events
"""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from djua_energy.alerting.service import build_alert_decision
from djua_energy.pipeline.inference import LocalInferenceEngine
from djua_energy.pipeline.synthetic_data import SyntheticTelemetryGenerator
from djua_energy.pipeline.contracts import validate_payload, validate_prediction_payload
from djua_energy.pipeline.features import build_maintenance_features, build_security_features
from djua_energy.ingestion.telemetry_service import TelemetryIngestionService
from djua_energy.chat.service import DjuaChatService
from djua_energy.database.realtime_store import RealtimeTelemetryStore
from djua_energy.features.payment_features import build_payment_features
from djua_energy.integration.backend_events import BackendResolvedEventsClient
from djua_energy.kit_intelligence.service import build_kit_intelligence
from djua_energy.solar_advisor.service import SolarAdvisorService
from djua_energy.scoring.service import CustomerScoringService

app = FastAPI(
    title="Djua Energy IoT Demo",
    version="0.1.0",
    description=(
        "API locale DJUA ENERGY pour ingestion IoT, maintenance predictive, securite, chat IA device "
        "et recommandation de kits solaires. Les schemas Swagger documentent les champs obligatoires, "
        "les champs optionnels utiles aux modeles et des exemples directement testables."
    ),
)
app.mount("/static", StaticFiles(directory="apps/api/static"), name="static")
engine = LocalInferenceEngine("artifacts")
realtime_store = RealtimeTelemetryStore()
telemetry_service = TelemetryIngestionService(engine, realtime_store=realtime_store)
chat_service = DjuaChatService(engine=engine)
solar_advisor_service = SolarAdvisorService()
customer_scoring_service: CustomerScoringService | None = None


def _customer_scoring_service() -> CustomerScoringService:
    global customer_scoring_service
    if customer_scoring_service is None:
        try:
            customer_scoring_service = CustomerScoringService()
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="Modele customer scoring absent. Lancez `python scripts/train_scoring.py`.",
            ) from exc
    return customer_scoring_service


TELEMETRY_RECORD_EXAMPLE = {
    "message_id": "msg-maint-001",
    "schema_version": "1.0",
    "message_type": "telemetry",
    "device_id": "device-demo-001",
    "kit_id": "kit-demo-001",
    "serial_number": "SN-DEMO-001",
    "event_time": "1786615200",
    "sequence_number": 1,
    "battery_voltage_v": 11.8,
    "battery_current_a": -4.2,
    "battery_power_w": -49.6,
    "state_of_charge_pct": 28,
    "state_of_health_pct": 71,
    "region": "urban_periurban",
    "season": "dry",
    "day_period": "day",
    "ambient_temperature_c": 34,
    "humidity_pct": 62,
    "installation_type": "household_rooftop",
    "charge_duration_seconds": 0,
    "discharge_duration_seconds": 1800,
    "solar_voltage_v": 18.4,
    "solar_current_a": 3.2,
    "solar_power_w": 58.8,
    "energy_generated_wh": 620,
    "solar_error_code": "NONE",
    "load_voltage_v": 12.1,
    "load_current_a": 5.8,
    "load_power_w": 70.2,
    "energy_consumed_wh": 950,
    "overload_detected": False,
    "latitude": -4.4419,
    "longitude": 15.2663,
    "geofence_status": "inside",
    "speed_mps": 0,
    "enclosure_opened": False,
    "connectivity_type": "lte",
    "network_operator": "orange",
    "device_temperature_c": 38,
    "missing_measurement_count": 0,
    "abnormal_consumption_detected": True,
    "battery_error_code": "NONE",
}

SOLAR_ADVISOR_REQUEST_EXAMPLE = {
    "customer_id": "client-demo",
    "city": "kinshasa",
    "region": "rdc-ouest",
    "housing_type": "menage urbain",
    "people_count": 5,
    "autonomy_hours": 10,
    "budget": 1800000,
    "preference": "balanced",
    "source": "swagger",
    "contact": {"phone": "+243000000000"},
    "appliances": [
        {
            "name": "television",
            "appliance_id": "television_led_32",
            "quantity": 1,
            "hours_per_day": 5,
            "usage_period": "night",
            "essential": True,
            "simultaneous": True,
        },
        {
            "name": "congelateur",
            "appliance_id": "freezer_small",
            "quantity": 1,
            "hours_per_day": 24,
            "usage_period": "continuous",
            "essential": True,
            "simultaneous": True,
        },
        {
            "name": "ampoule",
            "appliance_id": "led_bulb_9w",
            "quantity": 8,
            "hours_per_day": 6,
            "usage_period": "night",
            "essential": True,
            "simultaneous": True,
        },
    ],
}


class TelemetryRecord(BaseModel):
    """Mesure boitier utilisee par les predictions maintenance/securite."""

    model_config = {
        "extra": "allow",
        "json_schema_extra": {
            "example": TELEMETRY_RECORD_EXAMPLE,
        },
    }

    message_id: str = Field(..., description="Identifiant unique du message, utilise pour l'anti-doublon.")
    schema_version: str = Field(..., description="Version du contrat envoye par le boitier, par exemple 1.0.")
    message_type: Literal["telemetry"] = Field(
        ...,
        description="Type de message. Les endpoints de prediction attendent des mesures telemetry completes.",
    )
    device_id: str = Field(..., description="Identifiant unique du boitier IoT.")
    kit_id: str = Field(..., description="Identifiant du kit solaire rattache au boitier.")
    serial_number: str = Field(..., description="Numero de serie physique du boitier ou du kit.")
    event_time: str = Field(
        ...,
        description="Horodatage de la mesure. Dans le MVP, un timestamp Unix sous forme de chaine est recommande.",
    )
    sequence_number: int = Field(..., ge=1, description="Numero croissant du message pour ce boitier.")
    battery_voltage_v: float = Field(..., gt=0, description="Tension batterie en volts.")
    battery_current_a: float = Field(..., description="Courant batterie en amperes.")
    battery_power_w: float = Field(..., description="Puissance batterie en watts.")
    state_of_charge_pct: float = Field(..., ge=0, le=100, description="Niveau de charge batterie en pourcentage.")
    state_of_health_pct: float = Field(..., ge=0, le=100, description="Etat de sante batterie en pourcentage.")

    region: str | None = Field(None, description="Zone geographique ou profil regional.")
    season: Literal["dry", "rainy", "harmattan", "transition"] | None = Field(None, description="Saison locale.")
    day_period: Literal["day", "night"] | None = Field(None, description="Periode jour/nuit de la mesure.")
    ambient_temperature_c: float | None = Field(None, description="Temperature ambiante en degres Celsius.")
    humidity_pct: float | None = Field(None, ge=0, le=100, description="Humidite relative en pourcentage.")
    installation_type: str | None = Field(None, description="Type d'installation du kit.")

    charge_duration_seconds: float | None = Field(None, ge=0, description="Duree de charge recente.")
    discharge_duration_seconds: float | None = Field(None, ge=0, description="Duree de decharge recente.")
    solar_voltage_v: float | None = Field(None, description="Tension panneau/regulateur en volts.")
    solar_current_a: float | None = Field(None, description="Courant solaire en amperes.")
    solar_power_w: float | None = Field(None, description="Puissance solaire instantanee.")
    energy_generated_wh: float | None = Field(None, description="Energie solaire generee en Wh.")
    solar_error_code: str | None = Field(None, description="Code erreur solaire, NONE si aucun.")
    load_voltage_v: float | None = Field(None, description="Tension cote charge.")
    load_current_a: float | None = Field(None, description="Courant cote charge.")
    load_power_w: float | None = Field(None, description="Puissance consommee par les charges.")
    energy_consumed_wh: float | None = Field(None, description="Energie consommee en Wh.")
    overload_detected: bool | None = Field(None, description="Surcharge detectee.")

    latitude: float | None = Field(None, description="Latitude GPS.")
    longitude: float | None = Field(None, description="Longitude GPS.")
    geofence_status: Literal["inside", "outside", "unknown"] | None = Field(None, description="Statut geofence.")
    speed_mps: float | None = Field(None, description="Vitesse estimee en m/s.")
    enclosure_opened: bool | None = Field(None, description="Boitier ouvert.")

    connectivity_type: str | None = Field(None, description="Technologie reseau, ex: lte, gsm.")
    network_operator: str | None = Field(None, description="Operateur reseau.")
    device_temperature_c: float | None = Field(None, description="Temperature interne du boitier.")
    missing_measurement_count: int | None = Field(None, ge=0, description="Nombre de mesures manquantes.")
    abnormal_consumption_detected: bool | None = Field(None, description="Consommation anormale detectee.")
    battery_error_code: str | None = Field(None, description="Code erreur batterie, NONE si aucun.")
    device_error_code: str | None = Field(None, description="Code erreur general du device, NONE si aucun.")


class CustomerDecisionIdentityRequest(BaseModel):
    model_config = {"extra": "forbid"}

    client_id: str | None = None
    kit_id: str = Field(..., description="Identifiant du kit rattache au client.")
    device_id: str = Field(..., description="Identifiant du boitier IoT rattache au kit.")
    installation_id: str | None = None
    contract_id: str | None = None
    assignment_id: str | None = None
    resolution_status: Literal["resolved", "unresolved", "ambiguous", "conflict", "stale", "partial"] = Field(
        ...,
        description="Statut de resolution fourni par le backend metier. L'API IA ne resout pas l'identite.",
    )


class PaymentRecord(BaseModel):
    model_config = {"extra": "allow"}

    payment_id: str | None = Field(None, description="Identifiant du paiement cote backend/Orange.")
    client_id: str | None = Field(None, description="Identifiant client si present dans l'evenement paiement.")
    contract_id: str | None = Field(None, description="Contrat concerne par le paiement.")
    due_date: str | None = Field(None, description="Date d'echeance attendue.")
    paid_at: str | None = Field(None, description="Date de paiement effectif.")
    date: str | None = Field(None, description="Date de transaction si paid_at n'existe pas.")
    amount_due: float | None = Field(None, ge=0, description="Montant attendu.")
    amount_paid: float | None = Field(None, ge=0, description="Montant paye.")
    amountUSD: float | None = Field(None, ge=0, description="Alias historique du montant paye en USD.")
    days_late: float | None = Field(None, ge=0, description="Nombre de jours de retard. 0 si paye a temps.")
    status: str = Field(..., description="Statut brut: paid/completed/late/missed/failed/pending/etc.")
    method: str | None = Field(None, description="Methode de paiement, ex: orange_money.")


class CustomerDecisionRequest(BaseModel):
    """Snapshot Backend -> IA pour la decision client multidimensionnelle."""

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "example": {
                "schema_version": "1.0",
                "request_id": "req-123",
                "as_of": "2026-08-18T14:30:00+02:00",
                "identity": {
                    "client_id": "client-923",
                    "kit_id": "kit-034",
                    "device_id": "device-001",
                    "installation_id": "installation-674",
                    "contract_id": "contract-884",
                    "assignment_id": "assignment-889",
                    "resolution_status": "resolved",
                },
                "telemetry": {
                    "event_time": "2026-08-18T14:29:45+02:00",
                    "battery_temperature_c": 48.2,
                    "state_of_charge_pct": 32,
                    "state_of_health_pct": 78,
                    "connection_status": "connected",
                },
                "context": {
                    "region": "kinshasa",
                    "season": "dry",
                    "day_period": "afternoon",
                    "ambient_temperature_c": 33.8,
                },
                "payments": [
                    {
                        "payment_id": "pay-001",
                        "contract_id": "contract-884",
                        "client_id": "client-923",
                        "due_date": "2026-07-01T00:00:00+02:00",
                        "paid_at": "2026-07-01T12:00:00+02:00",
                        "days_late": 0,
                        "amount_due": 20,
                        "amount_paid": 20,
                        "status": "paid",
                        "method": "orange_money",
                    }
                ],
                "customer": {
                    "tenure_months": 18,
                    "active_contracts": 1,
                    "customer_segment": "residential",
                },
                "contract": {
                    "periodic_amount_usd": 20,
                    "status": "active",
                },
                "kit_intelligence": {
                    "maintenance_risk": 0.84,
                    "security_risk": 0.12,
                    "battery_health": "degraded",
                    "critical_anomaly": True,
                },
                "data_quality": {
                    "identity_resolved": True,
                    "telemetry_age_seconds": 15,
                    "missing_features": [],
                },
            }
        },
    }

    schema_version: str = Field(..., description="Version du contrat Backend -> IA.")
    request_id: str = Field(..., description="Identifiant de correlation.")
    as_of: str = Field(..., description="Instant du snapshot de decision.")
    identity: CustomerDecisionIdentityRequest = Field(
        ...,
        description="Identifiants client, kit, device, contrat et affectation.",
    )
    telemetry: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    payments: list[PaymentRecord] = Field(
        default_factory=list,
        description="Historique brut des paiements. L'API IA calcule les features payment depuis cette liste.",
    )
    payment: dict[str, Any] = Field(
        default_factory=dict,
        description="Compatibilite: features paiement deja calculees. Preferer payments[] brut.",
    )
    customer: dict[str, Any] = Field(default_factory=dict)
    contract: dict[str, Any] = Field(default_factory=dict)
    kit_intelligence: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)


class CustomerDecisionFromTelemetryRequest(CustomerDecisionRequest):
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "example": {
                "schema_version": "1.0",
                "request_id": "req-telemetry-001",
                "as_of": "2026-08-18T14:30:00+02:00",
                "identity": {
                    "client_id": "client-923",
                    "kit_id": "kit-034",
                    "device_id": "device-001",
                    "installation_id": "installation-674",
                    "contract_id": "contract-884",
                    "assignment_id": "assignment-889",
                    "resolution_status": "resolved",
                },
                "records": [TELEMETRY_RECORD_EXAMPLE],
                "payments": [
                    {
                        "payment_id": "pay-001",
                        "contract_id": "contract-884",
                        "client_id": "client-923",
                        "due_date": "2026-07-01T00:00:00+02:00",
                        "paid_at": "2026-07-01T12:00:00+02:00",
                        "days_late": 0,
                        "amount_due": 20,
                        "amount_paid": 20,
                        "status": "paid",
                        "method": "orange_money",
                    },
                    {
                        "payment_id": "pay-002",
                        "contract_id": "contract-884",
                        "client_id": "client-923",
                        "due_date": "2026-08-01T00:00:00+02:00",
                        "paid_at": "2026-08-14T12:00:00+02:00",
                        "days_late": 13,
                        "amount_due": 20,
                        "amount_paid": 20,
                        "status": "late",
                        "method": "orange_money",
                    },
                ],
                "customer": {
                    "tenure_months": 18,
                    "active_contracts": 1,
                    "customer_segment": "residential",
                },
                "contract": {
                    "periodic_amount_usd": 20,
                    "status": "active",
                },
                "data_quality": {
                    "identity_resolved": True,
                    "missing_features": [],
                    "warnings": [],
                },
            },
        },
    }

    records: list[TelemetryRecord] = Field(
        ...,
        min_length=1,
        description="Fenetre de telemetrie brute utilisee pour calculer maintenance/security avant scoring client.",
    )

    @model_validator(mode="after")
    def validate_backend_contract(self) -> "CustomerDecisionFromTelemetryRequest":
        identity = self.identity
        if identity.resolution_status == "resolved":
            required = [identity.client_id, identity.kit_id, identity.device_id]
            if any(not value for value in required):
                raise ValueError("resolved identity requires client_id, kit_id and device_id")
        for record in self.records:
            if record.device_id != identity.device_id or record.kit_id != identity.kit_id:
                raise ValueError("all telemetry records must match identity.kit_id and identity.device_id")
        return self



class BackendResolvedEventsSyncRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "backend_base_url": "http://127.0.0.1:9000",
                "cursor": None,
                "limit": 100,
                "ack": True,
            }
        }
    }

    backend_base_url: str = Field(..., description="URL racine du backend metier qui expose les snapshots resolus.")
    cursor: str | None = Field(None, description="Curseur de pagination fourni par le backend metier.")
    limit: int = Field(100, ge=1, le=500, description="Nombre maximum de snapshots resolus a consommer.")
    ack: bool = Field(True, description="Envoyer un ACK au backend apres chaque traitement.")
    resolved_events_path: str = Field(
        "/v1/ai/resolved-telemetry-events",
        description="Chemin backend qui liste les snapshots resolus.",
    )
    ack_path_template: str = Field(
        "/v1/ai/resolved-telemetry-events/{request_id}/ack",
        description="Chemin backend pour confirmer le traitement d'un snapshot.",
    )
    timeout_seconds: float = Field(15.0, gt=0, le=120, description="Timeout HTTP vers le backend metier.")


class TelemetryPredictionRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "records": [TELEMETRY_RECORD_EXAMPLE],
            },
        },
    }

    records: list[TelemetryRecord] = Field(
        ...,
        min_length=1,
        description="Fenetre de mesures telemetry a analyser. Envoyer 1 a 24 mesures recentes du meme boitier.",
    )


class TelemetryIngestionRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "records": [TELEMETRY_RECORD_EXAMPLE],
            },
        },
    }

    records: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description=(
            "Messages recus du boitier. Les messages invalides sont acceptes au niveau HTTP puis places en quarantaine "
            "par le service d'ingestion avec le detail des erreurs."
        ),
    )


class AiChatRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Parle-moi du device-0 et explique le risque maintenance.",
            },
        },
    }

    message: str = Field(..., min_length=1, description="Question en langage naturel sur un device ou la flotte.")


class KitConsoleChatRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Pourquoi ce kit est critique ?",
                "context": {
                    "payload": {"identity": {"kit_id": "kit-demo-001"}},
                    "prediction": {"decision": {"priority": "high"}},
                },
            },
        },
    }

    message: str = Field(..., min_length=1, description="Question posee depuis la console graphique du kit.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Dernier payload et derniere prediction produits par la console.",
    )


class SolarApplianceNeed(BaseModel):
    name: str = Field(..., description="Nom saisi par le client, ex: television, congelateur, ampoule.")
    appliance_id: str | None = Field(None, description="Identifiant catalogue si connu, ex: television_led_32.")
    quantity: int = Field(1, ge=1, description="Nombre d'appareils identiques.")
    hours_per_day: float | None = Field(None, ge=0, description="Heures d'utilisation par jour.")
    power_w: float | None = Field(None, ge=0, description="Puissance en watts si connue.")
    usage_period: Literal["day", "night", "mixed", "continuous"] = Field(
        "mixed",
        description="Periode habituelle d'utilisation.",
    )
    essential: bool = Field(True, description="Indique si l'appareil est indispensable.")
    simultaneous: bool = Field(True, description="Indique si l'appareil peut fonctionner avec les autres.")


class SolarContactInfo(BaseModel):
    model_config = {"extra": "allow"}

    name: str | None = Field(None, description="Nom du client.")
    phone: str | None = Field(None, description="Telephone du client.")
    email: str | None = Field(None, description="Email du client.")
    message: str | None = Field(None, description="Note libre pour le suivi commercial.")


class SolarAdvisorRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": SOLAR_ADVISOR_REQUEST_EXAMPLE,
        },
    }

    customer_id: str | None = Field(None, description="Identifiant client si deja connu.")
    city: str | None = Field(None, description="Ville du client.")
    region: str | None = Field(None, description="Region commerciale ou geographique.")
    housing_type: str | None = Field(None, description="Type de logement ou d'activite.")
    people_count: int | None = Field(None, ge=1, description="Nombre de personnes dans le foyer.")
    autonomy_hours: float | None = Field(None, ge=1, description="Autonomie souhaitee en heures.")
    budget: float | None = Field(None, ge=0, description="Budget indicatif dans la devise du catalogue.")
    preference: Literal["economy", "balanced", "performance", "autonomy"] = Field(
        "balanced",
        description=(
            "Priorite de recommandation: economy minimise le prix, balanced equilibre prix et confort, "
            "performance privilegie la puissance, autonomy privilegie les heures sans soleil."
        ),
    )
    appliances: list[SolarApplianceNeed] = Field(
        ...,
        min_length=1,
        description="Liste des appareils a alimenter.",
    )
    source: str = Field("manual", description="Origine de la demande: manual, swagger, frontend, conversation.")
    contact: SolarContactInfo = Field(default_factory=SolarContactInfo, description="Coordonnees optionnelles.")


class SolarConversationRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Je suis a Kinshasa avec 1 television, 1 congelateur, 8 ampoules et 10 heures autonomie.",
                "context": {},
            },
        },
    }

    message: str = Field(..., min_length=1, description="Message libre du client.")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Contexte retourne par l'appel precedent. Laisser vide au premier message.",
    )


class SolarContactRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Client Demo",
                "phone": "+243000000000",
                "email": "client@example.com",
                "message": "Merci de me rappeler pour finaliser le kit.",
            },
        },
    }

    name: str | None = Field(None, description="Nom du client.")
    phone: str | None = Field(None, description="Telephone du client.")
    email: str | None = Field(None, description="Email du client.")
    message: str | None = Field(None, description="Message ou instruction de rappel.")


class SolarExplanationRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "audience": "client",
            },
        },
    }

    audience: Literal["client", "technician", "sales"] = Field(
        "client",
        description=(
            "Public cible de l'explication: client pour une explication simple, technician pour plus de details techniques, "
            "sales pour une formulation commerciale orientee devis et prochaine action."
        ),
    )


class SolarQuestionRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "question": "Pourquoi me conseillez-vous ce nombre de panneaux et de batteries ?",
            },
        },
    }

    question: str = Field(..., description="Question posee par le client ou technicien a propos du devis calcule.")


def _records_to_dicts(payload: TelemetryPredictionRequest) -> list[dict]:
    return [_model_to_dict(record) for record in payload.records]


def _customer_records_to_dicts(payload: CustomerDecisionFromTelemetryRequest) -> list[dict]:
    return [_model_to_dict(record) for record in payload.records]


def _payment_records_to_dicts(payload: CustomerDecisionRequest) -> list[dict[str, Any]]:
    return [_model_to_dict(record) for record in payload.payments]


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _payment_features_from_payload(payload: CustomerDecisionRequest) -> dict[str, Any]:
    # Le backend envoie les paiements bruts; cette couche Data fabrique les features consommees par le scoring.
    raw_payments = _payment_records_to_dicts(payload)
    computed = build_payment_features(raw_payments, as_of=payload.as_of)
    if computed:
        return {**payload.payment, **computed}
    return dict(payload.payment)


def _customer_decision_snapshot(payload: CustomerDecisionRequest) -> dict[str, Any]:
    # Snapshot auditable: on conserve les paiements bruts et on injecte les features calculees.
    snapshot = _model_to_dict(payload)
    snapshot["raw_payments"] = snapshot.pop("payments", [])
    snapshot["payment"] = _payment_features_from_payload(payload)
    return snapshot


def _feature_snapshot_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    # Resume les tendances techniques qui expliquent les predictions maintenance/securite.
    maintenance_features = build_maintenance_features(records).iloc[-1].to_dict()
    security_features = build_security_features(records).iloc[-1].to_dict()
    return {
        "maintenance": {
            "battery_voltage_trend": round(float(maintenance_features.get("battery_voltage_trend", 0)), 3),
            "solar_load_ratio": round(float(maintenance_features.get("solar_load_ratio", 0)), 3),
        },
        "security": {
            "geofence_exit": round(float(security_features.get("geofence_exit", 0)), 3),
            "enclosure_opened": round(float(security_features.get("enclosure_opened", 0)), 3),
        },
    }


def _prediction_window_from_stored_history(
    records: list[dict[str, Any]],
    *,
    identity: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    # On stocke d'abord les nouvelles mesures, puis on relit l'historique pour predire sur une tendance.
    new_records, duplicate_records = realtime_store.insert_telemetry_records(records, identity=identity)
    latest = records[-1]
    device_id = str(latest.get("device_id", "unknown"))
    history_records = realtime_store.recent_records_for_device(device_id, limit=telemetry_service.sliding_window_size)
    return history_records or records[-telemetry_service.sliding_window_size :], {
        "incoming_records": len(records),
        "new_records": len(new_records),
        "duplicate_records": len(duplicate_records),
        "prediction_window_records": len(history_records) if history_records else min(len(records), telemetry_service.sliding_window_size),
    }


def _customer_decision_context_from_telemetry(payload: CustomerDecisionFromTelemetryRequest) -> dict:
    # Flux complet: telemetrie brute -> historique -> predictions kit -> contexte de scoring client.
    incoming_records = _customer_records_to_dicts(payload)
    for record in incoming_records:
        validation = validate_prediction_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)

    provided_identity = _model_to_dict(payload.identity)
    records, storage_summary = _prediction_window_from_stored_history(incoming_records, identity=provided_identity)
    latest = records[-1]
    maintenance_prediction = engine.infer_maintenance(records)
    security_prediction = engine.infer_security(records)
    alert_decision = build_alert_decision(
        device_id=str(latest.get("device_id", "unknown")),
        maintenance_prediction=maintenance_prediction,
        security_prediction=security_prediction,
        kit_id=latest.get("kit_id"),
        event_time=str(latest.get("event_time")),
    )
    alert_payload = asdict(alert_decision)
    feature_snapshot = _feature_snapshot_from_records(records)
    stored_prediction = realtime_store.save_prediction(
        device_id=str(latest.get("device_id", "unknown")),
        kit_id=latest.get("kit_id"),
        window_records=records,
        maintenance_prediction=maintenance_prediction,
        security_prediction=security_prediction,
        alert=alert_payload,
        feature_snapshot=feature_snapshot,
        identity=provided_identity,
    )
    kit_intelligence = build_kit_intelligence(
        records=records,
        inference_engine=engine,
        prediction_id=stored_prediction["prediction_id"],
        maintenance_prediction=maintenance_prediction,
        security_prediction=security_prediction,
    )
    maintenance_prediction = kit_intelligence["maintenance"]["raw_prediction"]
    security_prediction = kit_intelligence["security"]["raw_prediction"]
    identity_status = provided_identity.get("resolution_status")

    data_quality = dict(payload.data_quality)
    if data_quality.get("telemetry_age_seconds") is None:
        data_quality["telemetry_age_seconds"] = _telemetry_age_seconds(payload.as_of, latest.get("event_time"))
    data_quality.setdefault("missing_features", [])
    data_quality.setdefault("warnings", [])
    if identity_status != "resolved":
        # L'IA ne resout pas l'identite; elle degrade/bloque la decision si le backend ne l'a pas fait.
        data_quality["identity_resolved"] = False
        data_quality["missing_features"].append("identity")
        data_quality["warnings"].append(
            "Identity must be resolved by the backend before customer decision evaluation."
        )

    context = {
        "schema_version": payload.schema_version,
        "request_id": payload.request_id,
        "as_of": payload.as_of,
        "identity": provided_identity,
        "telemetry": {
            "event_time": latest.get("event_time"),
            "received_at": latest.get("received_at"),
            "battery_voltage_v": latest.get("battery_voltage_v"),
            "state_of_charge_pct": latest.get("state_of_charge_pct"),
            "state_of_health_pct": latest.get("state_of_health_pct"),
            "solar_power_w": latest.get("solar_power_w"),
            "load_power_w": latest.get("load_power_w"),
        },
        "context": {
            **payload.context,
            "region": payload.context.get("region", latest.get("region")),
            "season": payload.context.get("season", latest.get("season")),
            "day_period": payload.context.get("day_period", latest.get("day_period")),
            "ambient_temperature_c": payload.context.get(
                "ambient_temperature_c",
                latest.get("ambient_temperature_c"),
            ),
        },
        "payment": _payment_features_from_payload(payload),
        "raw_payments": _payment_records_to_dicts(payload),
        "customer": payload.customer,
        "contract": payload.contract,
        "kit_intelligence": {**kit_intelligence, **kit_intelligence["legacy_flat"], **payload.kit_intelligence},
        "data_quality": data_quality,
    }
    return {
        "context": context,
        "maintenance_prediction": maintenance_prediction,
        "security_prediction": security_prediction,
        "kit_intelligence": kit_intelligence,
        "stored_prediction": stored_prediction,
        "storage_summary": storage_summary,
        "feature_snapshot": feature_snapshot,
        "identity_status": identity_status or "unresolved",
    }


def _telemetry_age_seconds(as_of: str, event_time: Any) -> int | None:
    try:
        as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if isinstance(event_time, (int, float)):
            event_dt = datetime.fromtimestamp(float(event_time), tz=UTC)
        elif isinstance(event_time, str) and event_time.strip().isdigit():
            event_dt = datetime.fromtimestamp(float(event_time), tz=UTC)
        elif isinstance(event_time, str):
            event_dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        else:
            return None
    except (TypeError, ValueError):
        return None
    return max(0, int((as_of_dt - event_dt).total_seconds()))


DEMO_NOW = "2026-07-20T09:31:00Z"


def _metric(
    metric_id: str,
    label: str,
    value: float | int,
    unit: str,
    previous_value: float | int,
    trend: str,
    state: str,
    period: str = "today",
) -> dict:
    variation_abs = round(float(value) - float(previous_value), 2)
    variation_pct = round((variation_abs / float(previous_value)) * 100, 2) if previous_value else 0.0
    return {
        "id": metric_id,
        "label": label,
        "value": value,
        "unit": unit,
        "period": period,
        "previous_value": previous_value,
        "variation_absolute": variation_abs,
        "variation_percent": variation_pct,
        "trend": trend,
        "state": state,
        "last_updated_at": DEMO_NOW,
        "freshness": {"label": "Mis a jour il y a 2 minutes", "age_seconds": 120},
        "sparkline": [previous_value, round((previous_value + value) / 2, 2), value],
    }


def _source(kind: str, detail: str, model_name: str | None = None) -> dict:
    return {
        "kind": kind,
        "detail": detail,
        "model_name": model_name,
        "generated_at": DEMO_NOW,
    }


def _demo_windows() -> dict[str, list[dict]]:
    scenarios_by_kit = {
        "kit-0": "movement_then_connectivity_loss",
        "kit-1": "battery_overheating",
        "kit-2": "normal_operation",
    }
    records = SyntheticTelemetryGenerator(seed=31, num_kits=3).generate(
        scenarios=sorted(set(scenarios_by_kit.values())),
        duration_hours=3,
    )
    windows: dict[str, list[dict]] = {}
    for record in records:
        kit_id = str(record["kit_id"])
        if scenarios_by_kit.get(kit_id) == record.get("scenario"):
            windows.setdefault(kit_id, []).append(record)
    return windows


def _model_score(maintenance_prediction: dict, security_prediction: dict) -> int:
    maintenance_score = float(maintenance_prediction["technical_risk_probability"])
    security_score = float(security_prediction["suspicious_activity_score"])
    return round(max(maintenance_score, security_score) * 100)


def _severity_from_alert(priority: str) -> str:
    return "low" if priority == "none" else priority


def _decision_category(maintenance_prediction: dict, security_prediction: dict) -> str:
    maintenance_score = float(maintenance_prediction["technical_risk_probability"])
    security_score = float(security_prediction["suspicious_activity_score"])
    return "security" if security_score >= maintenance_score else "maintenance"


def _human_label_for_category(category: str) -> dict[str, str]:
    if category == "security":
        return {
            "title": "Suspicion de fraude",
            "type": "fraud_detection",
            "summary": "Le modele securite signale un comportement compatible avec une manipulation, un deplacement ou une perte de controle.",
            "recommendation": "Verifier le boitier, la position GPS et l'identite terrain.",
        }
    return {
        "title": "Prediction de maintenance",
        "type": "predictive_maintenance",
        "summary": "Le modele maintenance signale un risque technique sur le kit.",
        "recommendation": "Planifier une inspection technique preventive.",
    }


def _feature_snapshot(records: list[dict]) -> dict:
    maintenance_features = build_maintenance_features(records).iloc[-1].to_dict()
    security_features = build_security_features(records).iloc[-1].to_dict()
    selected = {
        "maintenance": {
            "battery_voltage_trend": round(float(maintenance_features.get("battery_voltage_trend", 0)), 3),
            "battery_temp_trend": round(float(maintenance_features.get("battery_temp_trend", 0)), 3),
            "max_battery_temp": round(float(maintenance_features.get("max_battery_temp", 0)), 3),
            "connectivity_gap": round(float(maintenance_features.get("connectivity_gap", 0)), 3),
            "solar_load_ratio": round(float(maintenance_features.get("solar_load_ratio", 0)), 3),
            "battery_age_months": round(float(maintenance_features.get("battery_age_months", 0)), 3),
        },
        "security": {
            "distance_to_installation": round(float(security_features.get("distance_to_installation", 0)), 3),
            "geofence_exit": round(float(security_features.get("geofence_exit", 0)), 3),
            "movement_then_gap": round(float(security_features.get("movement_then_gap", 0)), 3),
            "device_silence_duration": round(float(security_features.get("device_silence_duration", 0)), 3),
            "enclosure_opened": round(float(security_features.get("enclosure_opened", 0)), 3),
            "tamper_events": round(float(security_features.get("tamper_events", 0)), 3),
        },
    }
    return selected


def _score_history(records: list[dict]) -> list[dict]:
    history = []
    for index in range(1, len(records) + 1):
        window = records[:index]
        maintenance_prediction = engine.infer_maintenance(window)
        security_prediction = engine.infer_security(window)
        history.append({
            "timestamp": window[-1]["event_time"],
            "score": _model_score(maintenance_prediction, security_prediction),
            "maintenance_probability": maintenance_prediction["technical_risk_probability"],
            "security_probability": security_prediction["suspicious_activity_score"],
            "source": _source("model_output", "Score recalcule par les modeles maintenance et securite.", "LocalInferenceEngine"),
        })
    return history


def _risk_factors(records: list[dict], decision: dict) -> list[dict]:
    latest = records[-1]
    features = decision["feature_snapshot"]
    return [
        {
            "name": "technical_risk_probability",
            "label": "Probabilite de risque technique",
            "description": "Sortie directe du modele maintenance.",
            "observed_value": decision["model_outputs"]["maintenance"]["technical_risk_probability"],
            "expected_value": 0.65,
            "delta": round(float(decision["model_outputs"]["maintenance"]["technical_risk_probability"]) - 0.65, 3),
            "unit": "probability",
            "contribution": None,
            "importance_relative": "model_top_factor" if decision["category"] == "maintenance" else "supporting_signal",
            "direction": "increases_risk",
            "severity": decision["severity"],
            "category": "maintenance",
            "source": _source("model_output", "Probabilite retournee par infer_maintenance.", "maintenance"),
            "measured_at": DEMO_NOW,
        },
        {
            "name": "suspicious_activity_score",
            "label": "Score d'activite suspecte",
            "description": "Sortie directe du modele securite.",
            "observed_value": decision["model_outputs"]["security"]["suspicious_activity_score"],
            "expected_value": 0.65,
            "delta": round(float(decision["model_outputs"]["security"]["suspicious_activity_score"]) - 0.65, 3),
            "unit": "probability",
            "contribution": None,
            "importance_relative": "model_top_factor" if decision["category"] == "security" else "supporting_signal",
            "direction": "increases_risk",
            "severity": decision["severity"],
            "category": "security",
            "source": _source("model_output", "Score retourne par infer_security.", "security"),
            "measured_at": DEMO_NOW,
        },
        {
            "name": "connectivity_gap",
            "label": "Duree sans communication",
            "description": "Feature fournie au modele et calculee depuis la telemetrie.",
            "observed_value": features["maintenance"]["connectivity_gap"],
            "expected_value": 60,
            "delta": round(features["maintenance"]["connectivity_gap"] - 60, 3),
            "unit": "seconds",
            "contribution": None,
            "importance_relative": "explanatory_feature",
            "direction": "increases_risk",
            "severity": "high" if features["maintenance"]["connectivity_gap"] >= 300 else "low",
            "category": "connectivity",
            "source": _source("model_feature", "Feature presente dans le vecteur d'entree du modele.", "maintenance/security"),
            "measured_at": latest["event_time"],
        },
        {
            "name": "max_battery_temp",
            "label": "Temperature batterie maximale",
            "description": "Feature maintenance calculee sur la fenetre de telemetrie.",
            "observed_value": features["maintenance"]["max_battery_temp"],
            "expected_value": 40,
            "delta": round(features["maintenance"]["max_battery_temp"] - 40, 3),
            "unit": "celsius",
            "contribution": None,
            "importance_relative": "explanatory_feature",
            "direction": "increases_risk",
            "severity": "high" if features["maintenance"]["max_battery_temp"] >= 44 else "low",
            "category": "battery",
            "source": _source("model_feature", "Feature presente dans le vecteur d'entree du modele maintenance.", "maintenance"),
            "measured_at": latest["event_time"],
        },
        {
            "name": "movement_then_gap",
            "label": "Mouvement suivi d'une perte de connexion",
            "description": "Feature securite calculee avant inference.",
            "observed_value": features["security"]["movement_then_gap"],
            "expected_value": 0,
            "delta": features["security"]["movement_then_gap"],
            "unit": "binary",
            "contribution": None,
            "importance_relative": "explanatory_feature",
            "direction": "increases_risk",
            "severity": "high" if features["security"]["movement_then_gap"] else "low",
            "category": "security",
            "source": _source("model_feature", "Feature presente dans le vecteur d'entree du modele securite.", "security"),
            "measured_at": latest["event_time"],
        },
    ]


def _demo_entities() -> dict:
    windows = _demo_windows()

    kits = []
    alerts = []
    decisions = []
    interventions = []
    customers = []
    model_runs = []
    all_records = []
    for index, (kit_id, records) in enumerate(sorted(windows.items()), start=1):
        record = records[-1]
        maintenance_prediction = engine.infer_maintenance(records)
        security_prediction = engine.infer_security(records)
        alert_decision = build_alert_decision(
            device_id=str(record["device_id"]),
            maintenance_prediction=maintenance_prediction,
            security_prediction=security_prediction,
        )
        score = _model_score(maintenance_prediction, security_prediction)
        severity = _severity_from_alert(alert_decision.priority)
        category = _decision_category(maintenance_prediction, security_prediction)
        labels = _human_label_for_category(category)
        feature_snapshot = _feature_snapshot(records)
        client_id = f"client-{index:03d}"
        decision_id = f"decision-{index:03d}"
        alert_id = f"alert-{index:03d}"
        intervention_id = f"intervention-{index:03d}"
        health_score = max(0, 100 - score)
        status = "offline" if record.get("connection_status") == "disconnected" else "operational"
        model_run_id = f"model-run-{index:03d}"
        all_records.extend(records)
        model_runs.append({
            "model_run_id": model_run_id,
            "kit_id": kit_id,
            "device_id": record["device_id"],
            "records_used": len(records),
            "window_started_at": records[0]["event_time"],
            "window_ended_at": record["event_time"],
            "maintenance_model_version": maintenance_prediction["model_version"],
            "security_model_version": security_prediction["model_version"],
            "source": _source("model_output", "Execution reelle de LocalInferenceEngine sur une fenetre de telemetrie.", "LocalInferenceEngine"),
        })

        kit = {
            "kit_id": kit_id,
            "device_id": record["device_id"],
            "serial_number": record["serial_number"],
            "model": record.get("device_model", "djua-solar-v1"),
            "installation_type": record.get("installation_type"),
            "client_id": client_id,
            "client_name": f"Client demonstration {index}",
            "region": record.get("region"),
            "city": "Zone pilote",
            "country": "CI",
            "status": status,
            "connectivity_status": record.get("connection_status"),
            "health_score": health_score,
            "risk_level": severity,
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "gps_accuracy_m": record.get("gps_accuracy_m"),
            "last_telemetry_at": record["event_time"],
            "last_movement_at": record["event_time"] if record.get("movement_detected") else None,
            "active_alert_id": alert_id if severity != "low" else None,
            "active_intervention_id": intervention_id if severity in {"critical", "high"} else None,
            "model_score": score,
            "model_outputs": {
                "maintenance": maintenance_prediction,
                "security": security_prediction,
            },
            "source": _source("model_derived", "Statut de risque derive des sorties maintenance/security et de la priorisation d'alerte.", "LocalInferenceEngine"),
        }
        kits.append(kit)

        if severity != "low":
            alerts.append({
                "alert_id": alert_id,
                "decision_id": decision_id,
                "type": labels["type"],
                "title": labels["title"],
                "summary": labels["summary"],
                "severity": severity,
                "kit": {"kit_id": kit_id, "label": record["serial_number"]},
                "client": {"client_id": client_id, "name": f"Client demonstration {index}"},
                "location": {"country": "CI", "region": record.get("region"), "city": "Zone pilote"},
                "created_at": record["event_time"],
                "age_label": "2 min",
                "status": "open",
                "review_status": "pending_review",
                "assignee": "operations",
                "recommended_action": alert_decision.recommended_action,
                "is_new": True,
                "model_run_id": model_run_id,
                "source": _source("model_derived", "Alerte creee depuis build_alert_decision apres inference modele.", "LocalInferenceEngine"),
            })

        decisions.append({
            "decision_id": decision_id,
            "title": labels["title"],
            "category": category,
            "type": labels["type"],
            "severity": severity,
            "status": "open" if severity != "low" else "monitoring",
            "created_at": record["event_time"],
            "updated_at": record["event_time"],
            "kit_id": kit_id,
            "client_id": client_id,
            "region": record.get("region"),
            "model": {
                "name": "LocalInferenceEngine",
                "maintenance_version": maintenance_prediction["model_version"],
                "security_version": security_prediction["model_version"],
                "run_id": model_run_id,
            },
            "score": score,
            "probability": round(score / 100, 3),
            "confidence": 0.82,
            "predicted_class": severity,
            "threshold": 0.65,
            "summary": labels["summary"],
            "primary_recommendation": labels["recommendation"],
            "human_review": {"status": "pending", "required": severity != "low"},
            "model_outputs": {
                "maintenance": maintenance_prediction,
                "security": security_prediction,
                "alert_priority": alert_decision.__dict__,
            },
            "feature_snapshot": feature_snapshot,
            "source": _source("model_output", "Decision construite depuis les sorties directes des deux modeles locaux.", "LocalInferenceEngine"),
        })

        interventions.append({
            "intervention_id": intervention_id,
            "decision_id": decision_id,
            "kit_id": kit_id,
            "recommended_type": "fraud_check" if category == "security" else "preventive_maintenance",
            "priority": severity,
            "urgency": "same_day" if severity == "critical" else ("this_week" if severity == "high" else "monitoring"),
            "justification": f"Recommandation derivee du score modele {score}% et de la priorite {alert_decision.priority}.",
            "estimated_duration_minutes": 90 if category == "security" else 45,
            "estimated_cost": {"amount": 42 if category == "security" else 18, "currency": "EUR", "method": "demo_assumption_not_model_output"},
            "required_skills": ["diagnostic_iot", "controle_gps"] if category == "security" else ["maintenance_batterie"],
            "checklist": ["Verifier l'identite du kit", "Controler le boitier", "Comparer la position attendue"],
            "confidence": 0.8,
            "source": _source("model_derived", "Type et priorite derives de la decision IA; cout et duree sont des hypotheses demo.", "LocalInferenceEngine"),
        })

        customers.append({
            "client_id": client_id,
            "name": f"Client demonstration {index}",
            "risk_score": score,
            "risk_level": severity,
            "trend": "up" if severity != "low" else "stable",
            "model_version": "derived-from-kit-models",
            "confidence": 0.78,
            "summary": "Risque client derive du risque IA du kit rattache.",
            "main_factors": ["kit_model_score", "maintenance_prediction", "security_prediction"],
            "recommendations": ["Contacter le client", "Verifier la localisation"] if severity in {"critical", "high"} else ["Surveiller"],
            "source": _source("model_derived", "Aucun modele client separe n'existe encore; score client derive explicitement du score IA du kit.", "LocalInferenceEngine"),
        })

    return {
        "records": all_records,
        "windows": windows,
        "kits": kits,
        "alerts": alerts,
        "decisions": decisions,
        "interventions": interventions,
        "customers": customers,
        "model_runs": model_runs,
    }


def _not_found(entity: str, entity_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": f"{entity.upper()}_NOT_FOUND",
                "message": f"{entity} introuvable",
                "field": f"{entity}_id",
                "suggestion": "Verifier l'identifiant fourni.",
                "request_id": f"req-{entity_id}",
                "severity": "warning",
                "temporary": False,
            }
        },
    )


def _with_persisted_customer_decision(input_snapshot: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    stored = realtime_store.save_customer_decision(input_snapshot=input_snapshot, result=result)
    return {
        **result,
        "persistence": {
            "stored": True,
            "table": "customer_decision_history",
            "decision_id": stored["decision_id"],
            "created_at": stored["created_at"],
        },
    }


@app.get(
    "/health",
    summary="Verifier que l'API est demarree",
    description="Retourne un statut simple pour les tests, les probes AWS App Runner et la verification manuelle.",
)
@app.get("/", include_in_schema=False)
def frontend_home() -> FileResponse:
    return FileResponse("apps/api/static/kit_console.html")


def health() -> dict[str, str]:
    return {"status": "ok", "service": "djua-energy-iot-demo"}


@app.post(
    "/maintenance/predict",
    summary="Predire le risque de maintenance d'un boitier",
    description=(
        "Analyse une fenetre de mesures telemetry et retourne une prediction locale de maintenance predictive. "
        "A utiliser pour tester directement le modele maintenance sans passer par l'ingestion, la quarantaine ou l'audit."
    ),
)
def maintenance_predict(payload: TelemetryPredictionRequest) -> dict:
    records = _records_to_dicts(payload)
    for record in records:
        validation = validate_prediction_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)
    return engine.infer_maintenance(records)


@app.post(
    "/security/predict",
    summary="Predire le risque de securite ou fraude d'un boitier",
    description=(
        "Analyse une fenetre de mesures telemetry et retourne une prediction locale de securite: mouvement suspect, "
        "ouverture boitier, sortie de geofence, silence reseau ou signaux de fraude."
    ),
)
def security_predict(payload: TelemetryPredictionRequest) -> dict:
    records = _records_to_dicts(payload)
    for record in records:
        validation = validate_prediction_payload(record)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=validation)
    return engine.infer_security(records)


@app.post(
    "/telemetry/analyze",
    summary="Ingerer une fenetre telemetry et produire l'alerte IA complete",
    description=(
        "Flux principal du MVP IoT. L'endpoint valide les messages, met en quarantaine les invalides, ignore les doublons, "
        "execute les modeles maintenance et securite, construit une alerte priorisee, enregistre l'audit et met a jour les metriques."
    ),
)
def telemetry_analyze(payload: TelemetryIngestionRequest) -> dict:
    try:
        return telemetry_service.process_window(payload.records)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/ai/chat",
    summary="Poser une question en langage naturel sur un device",
    description=(
        "Assistant conversationnel pour interroger l'etat d'un boitier ou comprendre une prediction. "
        "Le MVP peut repondre avec le contexte local meme sans LLM externe."
    ),
)
def ai_chat(payload: AiChatRequest) -> dict:
    return chat_service.answer(payload.message).to_dict()


@app.get(
    "/telemetry/metrics",
    summary="Lire les metriques d'ingestion et de prediction",
    description="Retourne les compteurs en memoire: messages recus, quarantaines, doublons, predictions et alertes.",
)
def telemetry_metrics() -> dict:
    return telemetry_service.metrics.snapshot()


@app.get(
    "/telemetry/quarantine",
    summary="Lister les messages invalides mis en quarantaine",
    description="Retourne les payloads rejetes par la validation metier avec les erreurs detectees.",
)
def telemetry_quarantine() -> dict:
    return {"entries": [entry.__dict__ for entry in telemetry_service.quarantine_store.list_entries()]}


@app.get(
    "/telemetry/audit",
    summary="Lire le journal d'audit local",
    description="Retourne les evenements d'audit generes par l'ingestion: quarantaines, doublons et predictions terminees.",
)
def telemetry_audit() -> dict:
    return {"events": [event.__dict__ for event in telemetry_service.audit_log.list_events()]}


@app.get(
    "/solar-advisor/catalogs",
    summary="Lister les catalogues Solar Advisor",
    description=(
        "Retourne les appareils et composants solaires de demonstration utilises pour calculer la consommation, "
        "dimensionner le kit et construire le devis synthetique."
    ),
)
def solar_advisor_catalogs() -> dict:
    return solar_advisor_service.catalogs()


@app.post(
    "/solar-advisor/recommend",
    summary="Recommander un kit solaire a partir des besoins client",
    description=(
        "Calcule la consommation quotidienne des appareils, dimensionne panneaux/batteries/onduleur/regulateur, "
        "selectionne des composants de demonstration, genere une explication et sauvegarde la recommandation."
    ),
)
def solar_advisor_recommend(payload: SolarAdvisorRequest) -> dict:
    try:
        return solar_advisor_service.recommend(_model_to_dict(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/solar-advisor/conversation",
    summary="Guider un client en conversation vers une recommandation solaire",
    description=(
        "Transforme un message client en besoin structure. Renvoyer le champ context retourne par l'appel precedent "
        "pour conserver la conversation. Quand le client demande le devis et que les infos sont suffisantes, l'endpoint "
        "peut retourner une recommandation."
    ),
)
def solar_advisor_conversation(payload: SolarConversationRequest) -> dict:
    try:
        return solar_advisor_service.conversation_step(payload.message, payload.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/solar-advisor/recommendations",
    summary="Lister les recommandations Solar Advisor sauvegardees",
    description="Retourne les dernieres recommandations stockees localement dans SQLite, de la plus recente a la plus ancienne.",
)
def solar_advisor_recommendations(
    limit: Annotated[int, Query(
        ge=1,
        le=100,
        description="Nombre maximum de recommandations a retourner.",
        examples=[20],
    )] = 20,
) -> dict:
    return {"recommendations": solar_advisor_service.list_recommendations(limit=limit)}


@app.get(
    "/solar-advisor/recommendations/{recommendation_id}",
    summary="Lire le detail d'une recommandation Solar Advisor",
    description=(
        "Retourne la recommandation complete creee par /solar-advisor/recommend ou /solar-advisor/conversation: "
        "demande client, consommation, dimensionnement, composants, devis, hypotheses et limites."
    ),
)
def solar_advisor_recommendation_detail(
    recommendation_id: str = Path(
        ...,
        description=(
            "Identifiant retourne dans le champ recommendation_id apres la creation d'une recommandation. "
            "Exemple: solar-rec-123abc456def."
        ),
        examples=["solar-rec-123abc456def"],
    )
) -> dict:
    recommendation = solar_advisor_service.get_recommendation(recommendation_id)
    if recommendation is None:
        raise _not_found("solar recommendation", recommendation_id)
    return recommendation


@app.post(
    "/solar-advisor/recommendations/{recommendation_id}/contact",
    summary="Creer une demande de contact pour une recommandation solaire",
    description=(
        "Associe une demande de rappel commercial a une recommandation existante. Utiliser recommendation_id obtenu "
        "dans la reponse de /solar-advisor/recommend ou /solar-advisor/conversation."
    ),
)
def solar_advisor_contact(
    recommendation_id: str = Path(
        ...,
        description="Identifiant de la recommandation solaire a rattacher a la demande de contact.",
        examples=["solar-rec-123abc456def"],
    ),
    payload: SolarContactRequest = ...,
) -> dict:
    try:
        return solar_advisor_service.create_contact_request(recommendation_id, _model_to_dict(payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/solar-advisor/recommendations/{recommendation_id}/explain",
    summary="Expliquer une recommandation solaire deja creee",
    description=(
        "Retourne une explication lisible d'une recommandation existante. Si OPENAI_API_KEY est configuree, "
        "l'explication peut etre reformulee par IA; sinon l'API retourne une explication locale deterministe."
    ),
)
def solar_advisor_explain(
    recommendation_id: str = Path(
        ...,
        description=(
            "Identifiant retourne par /solar-advisor/recommend ou /solar-advisor/conversation. "
            "Il permet de retrouver le devis sauvegarde avant de generer l'explication."
        ),
        examples=["solar-rec-123abc456def"],
    ),
    payload: SolarExplanationRequest = ...,
) -> dict:
    try:
        return solar_advisor_service.explain_with_ai(recommendation_id, audience=payload.audience)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/solar-advisor/recommendations/{recommendation_id}/ask",
    summary="Poser une question interactive sur un devis solaire calcule",
    description=(
        "Permet de poser n'importe quelle question sur un devis genere (panneaux, batteries, onduleur, budget, meteo...). "
        "Le LLM repond en exploitant l'ensemble du contexte technique et financier du devis."
    ),
)
def solar_advisor_ask(
    recommendation_id: str = Path(
        ...,
        description="Identifiant de la recommandation solaire.",
        examples=["solar-rec-123abc456def"],
    ),
    payload: SolarQuestionRequest = ...,
) -> dict:
    try:
        return solar_advisor_service.answer_question(recommendation_id, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/solar-advisor",
    summary="Interface Web dediee DJUA AI Solar Advisor",
    description="Application Web moderne et interactive de conseil, dimensionnement et devis solaire intelligent.",
)
def solar_advisor_app() -> FileResponse:
    return FileResponse("apps/api/static/solar_advisor.html")


@app.get(
    "/frontend/solar-advisor",
    summary="Interface Web dediee DJUA AI Solar Advisor (alias frontend)",
    description="Application Web moderne et interactive de conseil, dimensionnement et devis solaire intelligent.",
)
def solar_advisor_frontend_app() -> FileResponse:
    return FileResponse("apps/api/static/solar_advisor.html")


@app.get(
    "/realtime/fleet-state",
    summary="Lire l'etat temps reel de la flotte",
    description="Retourne l'etat courant des devices connus dans le stockage temps reel local.",
)
def realtime_fleet_state() -> dict:
    states = realtime_store.list_device_states()
    return {
        "device_count": len(states),
        "states": states,
    }


@app.get(
    "/realtime/devices/{device_id}/state",
    summary="Lire l'etat temps reel d'un device",
    description="Retourne le dernier payload, la derniere prediction et le statut courant d'un boitier.",
)
def realtime_device_state(
    device_id: str = Path(
        ...,
        description="Identifiant du boitier IoT tel qu'envoye dans les payloads telemetry.",
        examples=["device-0"],
    )
) -> dict:
    state = realtime_store.get_device_state(device_id)
    if state is None:
        raise _not_found("device", device_id)
    return state


@app.get(
    "/realtime/devices/{device_id}/predictions",
    summary="Lister l'historique de predictions d'un device",
    description="Retourne les dernieres predictions maintenance/securite sauvegardees pour un boitier.",
)
def realtime_device_predictions(
    device_id: str = Path(
        ...,
        description="Identifiant du boitier IoT dont on veut consulter l'historique.",
        examples=["device-0"],
    ),
    limit: Annotated[int, Query(
        ge=1,
        le=500,
        description="Nombre maximum de predictions historiques a retourner.",
        examples=[50],
    )] = 50,
) -> dict:
    return {
        "device_id": device_id,
        "history": realtime_store.prediction_history(device_id, limit=limit),
    }


def _live_priority_rank(level: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}.get(str(level).lower(), 0)


def _live_state_summary(state: dict) -> dict:
    latest = state["latest_payload"]
    prediction = state["latest_prediction"]
    return {
        "device_id": state["device_id"],
        "kit_id": state["kit_id"],
        "region": latest.get("region"),
        "status": state["status"],
        "risk_level": state["risk_level"],
        "risk_score": state["risk_score"],
        "alert_priority": state["alert_priority"],
        "recommended_action": state["recommended_action"],
        "last_event_time": state["last_event_time"],
        "last_prediction_at": state["last_prediction_at"],
        "scenario": latest.get("scenario"),
        "battery": {
            "voltage_v": latest.get("battery_voltage_v"),
            "temperature_c": latest.get("battery_temperature_c"),
            "state_of_charge_pct": latest.get("state_of_charge_pct"),
            "state_of_health_pct": latest.get("state_of_health_pct"),
            "age_months": latest.get("battery_age_months"),
        },
        "energy": {
            "solar_power_w": latest.get("solar_power_w"),
            "load_power_w": latest.get("load_power_w"),
            "energy_generated_wh": latest.get("energy_generated_wh"),
            "energy_consumed_wh": latest.get("energy_consumed_wh"),
        },
        "environment": {
            "ambient_temperature_c": latest.get("ambient_temperature_c"),
            "humidity_pct": latest.get("humidity_pct"),
            "season": latest.get("season"),
            "day_period": latest.get("day_period"),
            "solar_irradiance_w_m2": latest.get("solar_irradiance_w_m2"),
        },
        "location": {
            "latitude": latest.get("latitude"),
            "longitude": latest.get("longitude"),
            "gps_accuracy_m": latest.get("gps_accuracy_m"),
            "distance_from_installation_m": latest.get("distance_from_installation_m"),
            "geofence_status": latest.get("geofence_status"),
        },
        "security": {
            "movement_detected": latest.get("movement_detected"),
            "tamper_detected": latest.get("tamper_detected"),
            "enclosure_opened": latest.get("enclosure_opened"),
            "impact_detected": latest.get("impact_detected"),
            "identity_mismatch_detected": latest.get("identity_mismatch_detected"),
        },
        "connectivity": {
            "type": latest.get("connectivity_type"),
            "status": latest.get("connection_status"),
            "network_quality": latest.get("network_quality"),
            "signal_strength_dbm": latest.get("signal_strength_dbm"),
            "connectivity_gap_seconds": latest.get("connectivity_gap_seconds"),
            "operator": latest.get("network_operator"),
        },
        "ai": {
            "prediction_id": prediction.get("prediction_id"),
            "records_used": prediction.get("records_used"),
            "maintenance_probability": prediction.get("maintenance_probability"),
            "security_probability": prediction.get("security_probability"),
            "maintenance_prediction": prediction.get("maintenance_prediction"),
            "security_prediction": prediction.get("security_prediction"),
            "feature_snapshot": prediction.get("feature_snapshot"),
        },
    }


def _kit_console_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    requested_domain = context.get("requested_domain") or "kit_diagnostic"
    payload = context.get("kit_payload") or context.get("payload") or {}
    kit_prediction = context.get("kit_prediction") or {}
    legacy_prediction = context.get("prediction") or {}
    client_scoring = context.get("client_scoring") or {}
    client_scoring_payload = context.get("client_scoring_payload") or {}
    prediction = kit_prediction or legacy_prediction
    records = payload.get("records") or []
    latest = records[-1] if records else {}
    payments = client_scoring_payload.get("payments") or payload.get("payments") or []
    kit_intelligence = prediction.get("kit_intelligence") or {}
    kit_source = client_scoring.get("kit_intelligence_source") or prediction.get("kit_intelligence_source") or {}
    maintenance = (
        kit_source.get("maintenance_prediction")
        or (kit_intelligence.get("maintenance") or {}).get("raw_prediction")
        or prediction.get("maintenance_prediction")
        or {}
    )
    security = (
        kit_source.get("security_prediction")
        or (kit_intelligence.get("security") or {}).get("raw_prediction")
        or prediction.get("security_prediction")
        or {}
    )
    kit_scores = prediction.get("scores") or {}
    client_scores = client_scoring.get("scores") or {}
    scores = client_scores if requested_domain == "client_scoring" and client_scores else kit_scores
    decision = (
        client_scoring.get("decision")
        if requested_domain == "client_scoring" and client_scoring.get("decision")
        else prediction.get("decision") or client_scoring.get("decision") or {}
    )
    return {
        "requested_domain": requested_domain,
        "identity": payload.get("identity") or prediction.get("identity") or {},
        "customer": client_scoring_payload.get("customer") or payload.get("customer") or {},
        "contract": client_scoring_payload.get("contract") or payload.get("contract") or {},
        "payments": payments,
        "payment_summary": _kit_console_payment_summary(payments),
        "latest_telemetry": latest,
        "scores": scores,
        "kit_scores": kit_scores,
        "client_scores": client_scores,
        "score_explanation_contract": {
            "client_value": "Score client calcule depuis le profil client, anciennete, contrats et contexte metier.",
            "payment_risk": "Score a expliquer uniquement depuis payments[]: retards, impayes, echecs, montants et dates de paiement.",
            "operational_risk": "Score a expliquer depuis les predictions maintenance/securite et la telemetrie du kit.",
            "intervention_priority": "Score final combinant payment_risk, operational_risk, valeur client et decision.",
            "important_rule": "Ne jamais justifier payment_risk par la tension batterie, la temperature, le mouvement ou le boitier ouvert.",
        },
        "decision": decision,
        "client_decision": client_scoring.get("decision") or {},
        "client_data_quality": client_scoring.get("data_quality") or {},
        "client_confidence": client_scoring.get("confidence"),
        "maintenance_prediction": maintenance,
        "security_prediction": security,
        "main_factors": _kit_console_risk_factors(latest, maintenance, security, scores),
    }


def _kit_console_focused_context(summary: dict[str, Any]) -> dict[str, Any]:
    domain = summary.get("requested_domain") or "kit_diagnostic"
    base = {
        "requested_domain": domain,
        "identity": summary.get("identity") or {},
        "score_explanation_contract": summary.get("score_explanation_contract") or {},
    }
    if domain == "client_scoring":
        return {
            **base,
            "customer": summary.get("customer") or {},
            "contract": summary.get("contract") or {},
            "payments": summary.get("payments") or [],
            "payment_summary": summary.get("payment_summary") or {},
            "client_scores": summary.get("client_scores") or summary.get("scores") or {},
            "client_decision": summary.get("client_decision") or summary.get("decision") or {},
            "client_data_quality": summary.get("client_data_quality") or {},
            "client_confidence": summary.get("client_confidence"),
            "operational_evidence": {
                "kit_scores": summary.get("kit_scores") or {},
                "maintenance_prediction": summary.get("maintenance_prediction") or {},
                "security_prediction": summary.get("security_prediction") or {},
                "main_factors": summary.get("main_factors") or [],
            },
            "strict_scope": (
                "Explique le scoring client en separant valeur client, risque paiement, risque operationnel "
                "et priorite. Ne justifie payment_risk qu'avec payments/payment_summary."
            ),
        }
    if domain == "maintenance":
        return {
            **base,
            "latest_telemetry": summary.get("latest_telemetry") or {},
            "maintenance_prediction": summary.get("maintenance_prediction") or {},
            "kit_scores": summary.get("kit_scores") or summary.get("scores") or {},
            "main_factors": summary.get("main_factors") or [],
            "strict_scope": "Reponds uniquement sur la maintenance du kit. Ne parle pas du scoring client ni du paiement.",
        }
    if domain == "security":
        return {
            **base,
            "latest_telemetry": summary.get("latest_telemetry") or {},
            "security_prediction": summary.get("security_prediction") or {},
            "kit_scores": summary.get("kit_scores") or summary.get("scores") or {},
            "main_factors": summary.get("main_factors") or [],
            "strict_scope": "Reponds uniquement sur la securite du kit. Ne parle pas du scoring client ni du paiement.",
        }
    return {
        **base,
        "latest_telemetry": summary.get("latest_telemetry") or {},
        "maintenance_prediction": summary.get("maintenance_prediction") or {},
        "security_prediction": summary.get("security_prediction") or {},
        "kit_scores": summary.get("kit_scores") or summary.get("scores") or {},
        "decision": summary.get("decision") or {},
        "main_factors": summary.get("main_factors") or [],
        "strict_scope": "Reponds sur le diagnostic kit. N'utilise le scoring client que si la question le demande explicitement.",
    }


def _kit_console_number(payload: dict[str, Any], name: str) -> float:
    value = payload.get(name)
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _kit_console_payment_summary(payments: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(payments)
    statuses = [str(payment.get("status") or "").lower() for payment in payments]
    paid = sum(1 for status in statuses if status in {"paid", "completed", "success", "successful"})
    days_late_values = [_kit_console_number(payment, "days_late") for payment in payments]
    late = sum(
        1
        for status, days_late in zip(statuses, days_late_values)
        if status == "late" or days_late > 0
    )
    missed = sum(1 for status in statuses if status == "missed")
    failed = sum(1 for status in statuses if status in {"failed", "rejected"})
    outstanding = sum(
        max(float(payment.get("amount_due") or 0) - float(payment.get("amount_paid") or 0), 0)
        for payment in payments
    )
    return {
        "payments_count": total,
        "paid_count": paid,
        "late_count": late,
        "missed_count": missed,
        "failed_count": failed,
        "payment_success_rate": round(paid / total, 4) if total else None,
        "average_days_late": round(sum(days_late_values) / late, 2) if late else 0.0,
        "outstanding_balance": round(outstanding, 2),
        "statuses": statuses,
    }


def _kit_console_is_payment_question(message: str) -> bool:
    normalized = message.lower()
    return any(
        word in normalized
        for word in ["paiement", "payment", "payeur", "impaye", "impayÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©", "retard", "echeance", "ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©chÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©ance"]
    )


def _kit_console_is_client_question(message: str) -> bool:
    normalized = message.lower()
    return any(word in normalized for word in ["client", "scoring", "score client", "valeur client"])


def _kit_console_is_technical_question(message: str) -> bool:
    normalized = message.lower()
    return any(
        word in normalized
        for word in [
            "kit",
            "maintenance",
            "securite",
            "sÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©curitÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©",
            "panne",
            "batterie",
            "reseau",
            "rÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©seau",
            "boitier",
            "boÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â®tier",
            "telemetrie",
            "tÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©lÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©mÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©trie",
            "critique",
        ]
    )


def _kit_console_detect_domain(message: str) -> str:
    if _kit_console_is_client_question(message):
        return "client_scoring"
    if _kit_console_is_payment_question(message):
        return "client_scoring"
    normalized = message.lower()
    if "maintenance" in normalized or "panne" in normalized or "batterie" in normalized:
        return "maintenance"
    if _kit_console_is_technical_question(message) and any(
        word in normalized for word in ["securite", "sÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©curitÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©", "boitier", "boÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â®tier", "tamper", "mouvement"]
    ):
        return "security"
    return "kit_diagnostic"


def _kit_console_risk_factors(
    latest: dict[str, Any],
    maintenance: dict[str, Any],
    security: dict[str, Any],
    scores: dict[str, Any],
) -> list[str]:
    factors: list[str] = []
    if float(latest.get("battery_temperature_c") or 0) >= 48:
        factors.append(f"temperature batterie elevee ({latest.get('battery_temperature_c')} C)")
    if float(latest.get("battery_voltage_v") or 99) <= 12.1:
        factors.append(f"tension batterie faible ({latest.get('battery_voltage_v')} V)")
    if float(latest.get("state_of_health_pct") or 100) <= 75:
        factors.append(f"sante batterie degradee ({latest.get('state_of_health_pct')}%)")
    if int(latest.get("connectivity_gap_seconds") or 0) >= 300:
        factors.append(f"coupure reseau longue ({latest.get('connectivity_gap_seconds')} secondes)")
    if latest.get("geofence_status") == "outside":
        factors.append("sortie de geofence")
    if latest.get("movement_detected"):
        factors.append("mouvement detecte")
    if latest.get("enclosure_opened") or latest.get("tamper_detected"):
        factors.append("boitier ouvert ou sabotage detecte")
    if latest.get("abnormal_consumption_detected"):
        factors.append("consommation anormale")
    if maintenance.get("suspected_component") not in {None, "", "none"}:
        factors.append(f"composant suspecte: {maintenance.get('suspected_component')}")
    if security.get("suspected_event_types"):
        factors.append(f"evenements securite: {', '.join(security.get('suspected_event_types'))}")
    if not factors and scores:
        factors.append("scores modele sous les seuils critiques")
    return factors or ["aucun facteur critique detecte"]


def _kit_console_local_chat_answer(message: str, context: dict[str, Any]) -> str:
    summary = _kit_console_context_summary(context)
    identity = summary["identity"]
    decision = summary["decision"]
    scores = summary["scores"]
    maintenance = summary["maintenance_prediction"]
    security = summary["security_prediction"]
    factors = summary["main_factors"]
    payment_summary = summary["payment_summary"]
    if not identity and not context.get("prediction"):
        return "Lance d'abord une prediction dans la console. Ensuite je pourrai expliquer le risque du kit saisi."
    if _kit_console_is_client_question(message) and not summary.get("client_scores"):
        return (
            "Lance d'abord le scoring client. Ensuite je pourrai expliquer separement la valeur client, "
            "le risque paiement, le risque operationnel du kit et la priorite d'intervention."
        )

    kit_id = identity.get("kit_id", "ce kit")
    client_id = identity.get("client_id", "ce client")
    priority = decision.get("priority", "non definie")
    action = decision.get("recommended_action", "surveillance")
    intro = (
        f"Pour {kit_id}, la priorite est {priority}. "
        f"L'action recommandee est: {action}."
    )
    risk_line = (
        " Scores: "
        f"maintenance={round(float(maintenance.get('technical_risk_probability') or 0) * 100)}%, "
        f"securite={round(float(security.get('suspicious_activity_score') or 0) * 100)}%, "
        f"operationnel={scores.get('operational_risk', 'n/a')}/100."
    )
    client_score_line = (
        " Scores client: "
        f"valeur_client={scores.get('client_value', 'n/a')}/100, "
        f"risque_paiement={scores.get('payment_risk', 'n/a')}/100, "
        f"risque_operationnel={scores.get('operational_risk', 'n/a')}/100, "
        f"priorite_intervention={scores.get('intervention_priority', 'n/a')}/100."
    )
    payment_line = (
        f" Le risque paiement de {scores.get('payment_risk', 'n/a')}/100 vient de payments[] pour {client_id}: "
        f"{payment_summary['payments_count']} paiement(s), "
        f"{payment_summary['late_count']} retard(s), "
        f"{payment_summary['missed_count']} impaye(s), "
        f"{payment_summary['failed_count']} echec(s), "
        f"taux de succes={payment_summary['payment_success_rate']}, "
        f"solde restant={payment_summary['outstanding_balance']}."
    )
    technical_factor_line = " Les raisons techniques principales du kit sont: " + "; ".join(factors) + "."
    if _kit_console_is_payment_question(message):
        return (
            payment_line
            + " Les signaux techniques du kit ne justifient pas ce score paiement; ils justifient plutot le risque operationnel."
        )
    if _kit_console_is_client_question(message):
        return intro + client_score_line + " " + payment_line.strip() + technical_factor_line
    if "que faire" in message.lower() or "action" in message.lower():
        return intro + " Je proposerais de verifier d'abord les facteurs les plus graves: " + "; ".join(factors) + "."
    return intro + risk_line + technical_factor_line


@app.get(
    "/demo/kit-console",
    summary="Interface graphique de demo pour tester un kit",
    description="Page HTML locale pour saisir les variables telemetry, lancer la prediction et discuter du resultat.",
)
def demo_kit_console() -> FileResponse:
    return FileResponse("apps/api/static/kit_console.html")


@app.post(
    "/demo/kit-console/chat",
    summary="Chat contextuel de la console kit",
    description="Repond a partir du dernier payload et de la derniere prediction de la console graphique.",
)
def demo_kit_console_chat(payload: KitConsoleChatRequest) -> dict:
    context = _kit_console_context_summary(payload.context)
    if not payload.context.get("requested_domain"):
        context["requested_domain"] = _kit_console_detect_domain(payload.message)
    focused_context = _kit_console_focused_context(context)
    if chat_service.llm_client.available:
        try:
            answer = chat_service.llm_client.generate(
                (
                    f"{payload.message}\n\n"
                    "Regles de reponse obligatoires: "
                    f"Le domaine detecte est {focused_context.get('requested_domain')}. "
                    "1) si la question parle du kit critique, de maintenance, securite, panne, batterie, reseau, "
                    "boitier ou telemetrie, explique uniquement avec latest_telemetry, maintenance_prediction, "
                    "security_prediction, main_factors et operational_risk. Ne parle pas du paiement dans ce cas. "
                    "2) si la question parle de risque paiement/payment_risk, explique uniquement avec payment_summary "
                    "et payments[]. N'utilise pas la batterie, la temperature, le mouvement ou le boitier pour justifier le paiement. "
                    "3) si la question parle du scoring client global, explique separement valeur client, paiement, operationnel "
                    "et priorite intervention. Si un champ manque, dis qu'il manque."
                ),
                focused_context,
            )
            return {
                "answer": answer,
                "used_llm": True,
                "context": focused_context,
                "sources": ["console_payload", "model_prediction", "OpenAIResponsesClient"],
            }
        except Exception as exc:  # noqa: BLE001 - demo endpoint must keep a local fallback.
            return {
                "answer": _kit_console_local_chat_answer(payload.message, payload.context),
                "used_llm": False,
                "error": str(exc),
                "context": focused_context,
                "sources": ["console_payload", "model_prediction", "local_fallback"],
            }
    return {
        "answer": _kit_console_local_chat_answer(payload.message, payload.context),
        "used_llm": False,
        "error": "OPENAI_API_KEY absente; reponse locale de secours utilisee.",
        "context": focused_context,
        "sources": ["console_payload", "model_prediction", "local_fallback"],
    }


@app.get(
    "/frontend/live/ui",
    summary="Construire le payload live complet pour l'interface",
    description=(
        "Endpoint agrÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â©gÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â© pour une interface temps reel: command center, decisions, digital twin, flotte, "
        "interventions, profil client, performance et administration."
    ),
)
def frontend_live_ui() -> dict:
    states = realtime_store.list_device_states()
    summaries = [_live_state_summary(state) for state in states]
    sorted_summaries = sorted(
        summaries,
        key=lambda item: (_live_priority_rank(item["risk_level"]), item["risk_score"]),
        reverse=True,
    )
    latest_predictions = [
        item
        for summary in sorted_summaries
        for item in realtime_store.prediction_history(summary["device_id"], limit=5)
    ]
    customers = realtime_store.list_customers(limit=500)
    customer_decisions = realtime_store.list_customer_decisions(limit=100)
    high_priority = [item for item in sorted_summaries if _live_priority_rank(item["risk_level"]) >= 2]
    priority_customer_decisions = [
        item for item in customer_decisions if _live_priority_rank(item.get("priority")) >= 2
    ]
    total_energy_generated_kwh = round(
        sum(float(item["energy"]["energy_generated_wh"] or 0) for item in summaries) / 1000,
        2,
    )
    offline_count = sum(1 for item in summaries if item["connectivity"]["status"] == "disconnected")
    average_health = round(
        sum(float(item["battery"]["state_of_health_pct"] or 0) for item in summaries) / len(summaries),
        2,
    ) if summaries else 0
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "meta": {
            "schema_version": "frontend-live.v1",
            "generated_at": generated_at,
            "source": "data/runtime/djua_realtime.sqlite",
            "ai_traceability": "Payload construit depuis device_state, prediction_history et telemetry_records.",
        },
        "command_center": {
            "summary": [
                {"id": "devices", "label": "Devices supervises", "value": len(summaries), "unit": "devices"},
                {"id": "priority_alerts", "label": "Alertes a traiter", "value": len(high_priority), "unit": "alerts"},
                {"id": "customers", "label": "Clients connus", "value": len(customers), "unit": "customers"},
                {"id": "customer_decisions", "label": "Decisions client", "value": len(customer_decisions), "unit": "decisions"},
                {"id": "offline", "label": "Devices hors ligne", "value": offline_count, "unit": "devices"},
                {"id": "battery_health", "label": "Sante batterie moyenne", "value": average_health, "unit": "%"},
                {"id": "energy_generated", "label": "Energie generee", "value": total_energy_generated_kwh, "unit": "kWh"},
            ],
            "priority_alerts": high_priority[:5],
            "recent_activity": latest_predictions[:10],
            "system_status": {"api": "online", "database": "online", "models": "loaded"},
        },
        "decision_detail": {
            "technical_predictions": latest_predictions,
            "customer_decisions": customer_decisions,
            "open_decision": customer_decisions[0] if customer_decisions else (latest_predictions[0] if latest_predictions else None),
        },
        "digital_twin": {
            "kits": sorted_summaries,
            "default_device_id": sorted_summaries[0]["device_id"] if sorted_summaries else None,
        },
        "fleet_monitoring": {
            "points": [
                {
                    "device_id": item["device_id"],
                    "kit_id": item["kit_id"],
                    "latitude": item["location"]["latitude"],
                    "longitude": item["location"]["longitude"],
                    "risk_level": item["risk_level"],
                    "risk_score": item["risk_score"],
                    "status": item["status"],
                    "connectivity_status": item["connectivity"]["status"],
                    "geofence_status": item["location"]["geofence_status"],
                    "region": item["region"],
                }
                for item in sorted_summaries
            ],
            "filters": ["region", "risk_level", "status", "connectivity_status", "geofence_status"],
        },
        "create_intervention": {
            "recommended_queue": [
                {
                    "device_id": item["device_id"],
                    "kit_id": item["kit_id"],
                    "priority": item["risk_level"],
                    "reason": item["scenario"],
                    "recommended_action": item["recommended_action"],
                }
                for item in high_priority
            ],
            "form_options": {
                "priorities": ["low", "medium", "high", "critical"],
                "statuses": ["draft", "assigned", "in_progress", "completed"],
                "intervention_types": ["battery_check", "security_check", "connectivity_check", "solar_panel_check"],
            },
        },
        "customer_profile": {
            "customers": customers,
            "recent_decisions": customer_decisions[:10],
            "priority_decisions": priority_customer_decisions[:10],
            "available_filters": ["client_id", "kit_id", "device_id", "priority", "customer_segment"],
            "source": "customers + customer_decision_history",
        },
        "performance": {
            "model_runs": len(latest_predictions),
            "customer_decision_runs": len(customer_decisions),
            "alerts_by_level": {
                level: sum(1 for item in summaries if item["risk_level"] == level)
                for level in ["critical", "high", "medium", "low"]
            },
            "energy_generated_kwh": total_energy_generated_kwh,
            "average_battery_health_pct": average_health,
        },
        "administration": {
            "models": engine.metadata,
            "data_tables": [
                "telemetry_records",
                "prediction_history",
                "device_state",
                "customers",
                "customer_decision_history",
            ],
            "ingestion_contract": "schemas/telemetry.v1.schema.json",
        },
    }


@app.post(
    "/demo/generate",
    summary="Generer quelques payloads telemetry de demonstration",
    description="Retourne trois mesures synthetiques pour comprendre le format attendu par les endpoints telemetry.",
)
def demo_generate() -> dict:
    generator = SyntheticTelemetryGenerator(seed=11, num_kits=2)
    records = generator.generate(scenarios=["normal_operation", "suspicious_movement"], duration_hours=2)
    return {"records": records[:3]}


@app.get(
    "/frontend/command-center",
    summary="Payload frontend du command center",
    description="Retourne KPI, alertes prioritaires, carte flotte, decisions IA, statut systeme et activite recente.",
)
def frontend_command_center() -> dict:
    demo = _demo_entities()
    kits = demo["kits"]
    alerts = demo["alerts"]
    operational = sum(1 for kit in kits if kit["status"] == "operational")
    at_risk = sum(1 for kit in kits if kit["risk_level"] in {"critical", "high"})
    offline = sum(1 for kit in kits if kit["status"] == "offline")
    by_severity = {
        "critical": sum(1 for decision in demo["decisions"] if decision["severity"] == "critical"),
        "high": sum(1 for decision in demo["decisions"] if decision["severity"] == "high"),
        "medium": sum(1 for decision in demo["decisions"] if decision["severity"] == "medium"),
        "low": sum(1 for decision in demo["decisions"] if decision["severity"] == "low"),
    }
    energy_today = round(sum(float(record.get("energy_generated_wh", 0)) for record in demo["records"]) / 1000, 2)
    return {
        "meta": {
            "schema_version": "frontend.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Les scores, decisions et alertes viennent de LocalInferenceEngine; les KPI energie viennent de la telemetrie; les couts/MTTR restent des hypotheses demo.",
            "model_runs": demo["model_runs"],
        },
        "summary": [
            {**_metric("total_kits", "Kits supervises", len(kits), "count", len(kits), "stable", "neutral"), "source": _source("telemetry_derived", "Comptage des kits dans les fenetres de demo.")},
            {**_metric("operational_kits", "Kits operationnels", operational, "count", max(0, operational - 1), "up", "positive"), "source": _source("telemetry_derived", "Derive du statut de connectivite de la derniere telemetrie.")},
            {**_metric("at_risk_kits", "Kits a risque", at_risk, "count", max(0, at_risk - 1), "up", "negative"), "source": _source("model_derived", "Nombre de kits dont la priorite modele est high ou critical.", "LocalInferenceEngine")},
            {**_metric("offline_kits", "Kits hors ligne", offline, "count", 0, "up", "negative"), "source": _source("telemetry_derived", "Derive de connection_status.")},
            {**_metric("availability_rate", "Disponibilite", round(operational / len(kits) * 100, 1), "percent", 96.5, "down", "negative"), "source": _source("telemetry_derived", "Calcule depuis les statuts de connectivite.")},
            {**_metric("energy_today", "Energie generee aujourd'hui", energy_today, "kWh", round(energy_today * 0.92, 2), "up", "positive"), "source": _source("telemetry_derived", "Somme de energy_generated_wh dans la telemetrie.")},
            {**_metric("co2_avoided", "CO2 evite", round(energy_today * 0.61, 2), "kg", round(energy_today * 0.56, 2), "up", "positive"), "source": _source("telemetry_derived", "Conversion demo a partir de l'energie mesuree; pas une sortie modele.")},
            {**_metric("open_ai_decisions", "Decisions IA ouvertes", sum(1 for decision in demo["decisions"] if decision["status"] == "open"), "count", 2, "up", "neutral"), "source": _source("model_derived", "Decisions ouvertes issues des predictions IA.", "LocalInferenceEngine")},
        ],
        "priority_alerts": alerts,
        "fleet_map": {
            "points": kits,
            "clusters": [{"cluster_id": "cluster-west", "count": len(kits), "risk_level": "high", "latitude": kits[0]["latitude"], "longitude": kits[0]["longitude"]}],
            "heatmaps": [{"type": "risk", "label": "Zones de risque", "points": [{"latitude": kit["latitude"], "longitude": kit["longitude"], "weight": kit["health_score"]} for kit in kits]}],
            "available_filters": ["country", "region", "city", "status", "risk_level", "connectivity_status", "installation_type", "model", "active_intervention_id"],
        },
        "decision_engine": {
            "total": len(demo["decisions"]),
            "by_severity": by_severity,
            "by_status": {
                "open": sum(1 for decision in demo["decisions"] if decision["status"] == "open"),
                "monitoring": sum(1 for decision in demo["decisions"] if decision["status"] == "monitoring"),
            },
            "confirmation_rate": {"value": None, "unit": "percent", "source": _source("not_available", "Pas encore de feedback humain persiste.")},
            "false_positive_rate": {"value": None, "unit": "percent", "source": _source("not_available", "Pas encore de feedback humain persiste.")},
            "average_review_time": {"value": None, "unit": "minutes", "source": _source("not_available", "Pas encore de workflow de revue persiste.")},
            "source": _source("model_derived", "Aggregation des decisions produites par les modeles locaux.", "LocalInferenceEngine"),
        },
        "system_status": [
            {"service": "ingestion", "status": "ok", "message": "Telemetry recue", "availability_percent": 99.9, "last_checked_at": DEMO_NOW, "response_time_ms": 18, "impact": "none"},
            {"service": "ai_service", "status": "ok", "message": "Modeles charges", "availability_percent": 99.5, "last_checked_at": DEMO_NOW, "response_time_ms": 41, "impact": "none"},
            {"service": "iot_connectivity", "status": "degraded", "message": "Un kit hors ligne dans la demo", "availability_percent": 92.0, "last_checked_at": DEMO_NOW, "response_time_ms": 120, "impact": "medium"},
        ],
        "recent_activity": [
            {"event_id": "evt-001", "type": "new_decision", "title": "Decision IA creee", "description": "Suspicion de fraude detectee.", "timestamp": DEMO_NOW, "actor": "djua-risk-engine", "entity": {"type": "decision", "id": "decision-001"}, "severity": "critical", "status": "open"},
            {"event_id": "evt-002", "type": "kit_offline", "title": "Kit hors ligne", "description": "Perte de communication prolongee.", "timestamp": DEMO_NOW, "actor": "iot-ingestion", "entity": {"type": "kit", "id": "kit-0"}, "severity": "high", "status": "open"},
        ],
    }


@app.get(
    "/frontend/decisions/{decision_id}",
    summary="Payload frontend du detail d'une decision IA",
    description="Retourne la decision IA, ses preuves, facteurs de risque, historique de score et options de feedback.",
)
def frontend_decision_detail(
    decision_id: str = Path(
        ...,
        description="Identifiant de decision retourne par le command center.",
        examples=["decision-001"],
    )
) -> dict:
    demo = _demo_entities()
    decision = next((item for item in demo["decisions"] if item["decision_id"] == decision_id), None)
    if decision is None:
        raise _not_found("decision", decision_id)
    kit = next(item for item in demo["kits"] if item["kit_id"] == decision["kit_id"])
    records = demo["windows"][decision["kit_id"]]
    risk_factors = _risk_factors(records, decision)
    return {
        "meta": {
            "schema_version": "decision.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "La decision, le score et les sorties brutes viennent du modele. Les facteurs sont les sorties modele et features d'entree; ce ne sont pas encore des valeurs SHAP.",
        },
        "decision": decision,
        "natural_language_explanation": {
            "title": "Ce qui s'est passe",
            "text": (
                f"Le moteur IA a analyse {len(records)} mesures du kit {decision['kit_id']}. "
                f"Le modele maintenance retourne une probabilite de {decision['model_outputs']['maintenance']['technical_risk_probability']} "
                f"et le modele securite retourne un score de {decision['model_outputs']['security']['suspicious_activity_score']}. "
                f"La decision finale est classee {decision['severity']} avec un score consolide de {decision['score']}%. "
                "Les facteurs affiches ci-dessous correspondent aux sorties modele et aux features calculees avant inference."
            ),
        },
        "risk_factors": risk_factors,
        "score_history": {
            "granularity": "30m",
            "thresholds": [{"label": "action", "value": 65}],
            "series": _score_history(records),
            "source": _source("model_output", "Chaque point est recalcule par les modeles sur un prefixe de la fenetre.", "LocalInferenceEngine"),
        },
        "evidence": [
            {"type": "model_output", "source": "maintenance", "value": decision["model_outputs"]["maintenance"], "timestamp": DEMO_NOW, "reliability": "synthetic_model", "relevance": "strong", "explanation": "Sortie brute du modele maintenance local."},
            {"type": "model_output", "source": "security", "value": decision["model_outputs"]["security"], "timestamp": DEMO_NOW, "reliability": "synthetic_model", "relevance": "strong", "explanation": "Sortie brute du modele securite local."},
            {"type": "model_features", "source": "feature_pipeline", "value": decision["feature_snapshot"], "timestamp": records[-1]["event_time"], "reliability": "derived_from_telemetry", "relevance": "strong", "explanation": "Features calculees avant inference et utilisees pour expliquer la decision."},
            {"type": "telemetry", "source": "iot_synthetic", "value": records[-1], "timestamp": records[-1]["event_time"], "reliability": "synthetic_demo", "relevance": "medium", "explanation": "Derniere mesure brute de la fenetre analysee."},
        ],
        "timeline": [
            {"timestamp": records[0]["event_time"], "type": "telemetry_received", "title": "Debut de fenetre telemetrie", "status": "done", "source": _source("telemetry", "Premier record utilise par le modele.")},
            {"timestamp": records[-1]["event_time"], "type": "features_computed", "title": "Features calculees", "status": "done", "source": _source("model_feature", "build_maintenance_features et build_security_features.")},
            {"timestamp": DEMO_NOW, "type": "model_inference", "title": "Inference maintenance et securite executee", "status": "done", "source": _source("model_output", "engine.infer_maintenance et engine.infer_security.", "LocalInferenceEngine")},
            {"timestamp": DEMO_NOW, "type": "decision_generated", "title": "Decision IA generee", "status": decision["status"], "source": decision["source"]},
        ],
        "recommendations": [next(item for item in demo["interventions"] if item["decision_id"] == decision_id)],
        "feedback_options": ["confirmed", "rejected", "false_positive", "fraud_confirmed", "failure_confirmed", "no_anomaly"],
    }


@app.get(
    "/frontend/interventions/create",
    summary="Preparer le formulaire frontend de creation d'intervention",
    description="Retourne le contexte de decision, un brouillon d'intervention, les options de formulaire et les regles de validation.",
)
def frontend_create_intervention(
    decision_id: Annotated[str, Query(
        description="Decision IA a transformer en brouillon d'intervention.",
        examples=["decision-001"],
    )] = "decision-001",
) -> dict:
    demo = _demo_entities()
    decision = next((item for item in demo["decisions"] if item["decision_id"] == decision_id), None)
    if decision is None:
        raise _not_found("decision", decision_id)
    kit = next(item for item in demo["kits"] if item["kit_id"] == decision["kit_id"])
    customer = next(item for item in demo["customers"] if item["client_id"] == decision["client_id"])
    recommendation = next(item for item in demo["interventions"] if item["decision_id"] == decision_id)
    related_alert = next((item for item in demo["alerts"] if item["decision_id"] == decision_id), None)
    priority = recommendation["priority"]
    default_due_at = "2026-07-20T16:00:00Z" if priority == "critical" else "2026-07-22T16:00:00Z"
    default_technician_id = "tech-001" if recommendation["recommended_type"] == "fraud_check" else "tech-002"
    return {
        "meta": {
            "schema_version": "create-intervention.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Le kit, la priorite, le motif et la justification viennent de la decision IA; techniciens, couts et planning sont des donnees demo non connectees a un outil terrain Orange.",
        },
        "context": {
            "decision": decision,
            "alert": related_alert,
            "kit": kit,
            "customer": customer,
            "source": _source("model_derived", "Contexte pre-rempli depuis la decision IA et le kit rattache.", "LocalInferenceEngine"),
        },
        "draft": {
            "intervention_id": recommendation["intervention_id"],
            "decision_id": decision_id,
            "kit_id": kit["kit_id"],
            "client_id": customer["client_id"],
            "type": recommendation["recommended_type"],
            "priority": priority,
            "urgency": recommendation["urgency"],
            "status": "draft",
            "reason": decision["summary"],
            "justification": recommendation["justification"],
            "assigned_team": "field-security" if recommendation["recommended_type"] == "fraud_check" else "field-maintenance",
            "assigned_technician_id": default_technician_id,
            "scheduled_start_at": None,
            "due_at": default_due_at,
            "estimated_duration_minutes": recommendation["estimated_duration_minutes"],
            "estimated_cost": recommendation["estimated_cost"],
            "required_skills": recommendation["required_skills"],
            "checklist": recommendation["checklist"],
            "source": recommendation["source"],
        },
        "form_options": {
            "types": [
                {"value": "fraud_check", "label": "Controle fraude / deplacement", "default_for": ["security"]},
                {"value": "preventive_maintenance", "label": "Maintenance preventive", "default_for": ["maintenance"]},
                {"value": "battery_replacement", "label": "Remplacement batterie", "default_for": ["maintenance"]},
                {"value": "connectivity_diagnostic", "label": "Diagnostic connectivite", "default_for": ["connectivity", "security"]},
            ],
            "priorities": ["critical", "high", "medium", "low"],
            "urgencies": ["same_day", "next_day", "this_week", "monitoring"],
            "teams": [
                {"team_id": "field-security", "label": "Equipe controle terrain", "skills": ["diagnostic_iot", "controle_gps"]},
                {"team_id": "field-maintenance", "label": "Equipe maintenance solaire", "skills": ["maintenance_batterie", "diagnostic_iot"]},
            ],
            "technicians": [
                {"technician_id": "tech-001", "name": "Technicien demo A", "team_id": "field-security", "region": kit["region"], "skills": ["diagnostic_iot", "controle_gps"], "availability": "available", "source": _source("demo_static", "Technicien fictif pour la demonstration.")},
                {"technician_id": "tech-002", "name": "Technicien demo B", "team_id": "field-maintenance", "region": kit["region"], "skills": ["maintenance_batterie", "diagnostic_iot"], "availability": "available", "source": _source("demo_static", "Technicien fictif pour la demonstration.")},
            ],
            "time_slots": [
                {"slot_id": "slot-001", "start_at": "2026-07-20T13:00:00Z", "end_at": "2026-07-20T15:00:00Z", "capacity": 1, "source": _source("demo_static", "Planning terrain non connecte.")},
                {"slot_id": "slot-002", "start_at": "2026-07-21T09:00:00Z", "end_at": "2026-07-21T11:00:00Z", "capacity": 2, "source": _source("demo_static", "Planning terrain non connecte.")},
            ],
        },
        "validation_rules": [
            {"field": "kit_id", "rule": "required"},
            {"field": "type", "rule": "required"},
            {"field": "priority", "rule": "required"},
            {"field": "assigned_technician_id", "rule": "required_before_confirm"},
            {"field": "scheduled_start_at", "rule": "required_before_confirm"},
        ],
        "actions": [
            {"id": "save_draft", "label": "Sauvegarder brouillon", "enabled": True, "method": "POST", "endpoint": None, "source": _source("not_available", "Pas encore de persistance intervention.")},
            {"id": "confirm_intervention", "label": "Confirmer intervention", "enabled": False, "method": "POST", "endpoint": None, "disabled_reason": "Creation persistante non implementee dans le MVP actuel.", "source": _source("not_available", "Workflow d'ecriture a ajouter cote backend.")},
        ],
    }


@app.get(
    "/frontend/kits/{kit_id}/digital-twin",
    summary="Payload frontend du jumeau numerique d'un kit",
    description="Retourne identite, sante, batterie, solaire, charge, connectivite, securite physique et prediction maintenance.",
)
def frontend_kit_digital_twin(
    kit_id: str = Path(
        ...,
        description="Identifiant du kit solaire tel qu'affiche dans la flotte ou le command center.",
        examples=["kit-0"],
    )
) -> dict:
    demo = _demo_entities()
    kit = next((item for item in demo["kits"] if item["kit_id"] == kit_id), None)
    if kit is None:
        raise _not_found("kit", kit_id)
    records = demo["windows"][kit_id]
    latest = records[-1]
    return {
        "meta": {
            "schema_version": "kit-digital-twin.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Sante et maintenance_prediction derivent des sorties modele; mesures batterie/solaire/connectivite viennent de la derniere telemetrie.",
        },
        "identity": {**kit, "firmware": {"version": "1.0.0", "status": "up_to_date"}, "uptime": {"value": 99.1, "unit": "percent"}},
        "health": {"score": kit["health_score"], "level": kit["risk_level"], "trend": "down" if kit["risk_level"] != "low" else "stable", "confidence": 0.81, "prediction_horizon": "7d", "recommendation": kit["model_outputs"]["maintenance"]["recommended_action"], "source": _source("model_derived", "Score sante = 100 - score de risque modele consolide.", "LocalInferenceEngine")},
        "battery": {"voltage": {"value": latest["battery_voltage_v"], "unit": "V"}, "temperature": {"value": latest["battery_temperature_c"], "unit": "celsius"}, "soc": {"value": latest["state_of_charge_pct"], "unit": "percent"}, "soh": {"value": latest["state_of_health_pct"], "unit": "percent"}, "status": "watch" if kit["risk_level"] != "low" else "ok", "source": _source("telemetry", "Derniere telemetrie du kit.")},
        "solar": {"power": {"value": latest["solar_power_w"], "unit": "W"}, "energy_today": {"value": round(float(latest["energy_generated_wh"]) / 1000, 3), "unit": "kWh"}, "yield": {"value": round(float(latest["solar_power_w"]) / max(float(latest["solar_irradiance_w_m2"]), 1) * 100, 2), "unit": "percent"}, "status": "ok", "source": _source("telemetry_derived", "Mesures et ratio calcules depuis la telemetrie.")},
        "load": {"power": {"value": latest["load_power_w"], "unit": "W"}, "profile": latest["usage_profile"], "abnormal_consumption": latest["abnormal_consumption_detected"], "status": "watch" if latest["abnormal_consumption_detected"] else "ok", "source": _source("telemetry", "Derniere telemetrie du kit.")},
        "connectivity": {"network": latest["connectivity_type"], "status": kit["connectivity_status"], "signal_strength_dbm": latest["signal_strength_dbm"], "last_communication_at": latest["last_successful_sync_at"], "packet_loss_ratio": latest["packet_loss_ratio"], "source": _source("telemetry", "Derniere telemetrie du kit.")},
        "physical_security": {"movement_detected": latest["movement_detected"], "enclosure_opened": latest["enclosure_opened"], "geofence_status": latest["geofence_status"], "risk_level": kit["risk_level"], "source": _source("model_derived", "Risque securite derive du modele, signaux bruts depuis telemetrie.", "security")},
        "location": {"latitude": kit["latitude"], "longitude": kit["longitude"], "accuracy_m": kit["gps_accuracy_m"], "city": kit["city"], "region": kit["region"], "country": kit["country"], "geofence_status": latest["geofence_status"], "source": _source("telemetry", "Position GPS de la derniere telemetrie.")},
        "components": [
            {"name": "battery", "type": "storage", "status": "watch" if kit["model_outputs"]["maintenance"]["risk_level"] == "high" else "ok", "health_score": kit["health_score"], "current_value": latest["battery_voltage_v"], "unit": "V", "risk": kit["model_outputs"]["maintenance"]["risk_level"], "recommendation": kit["model_outputs"]["maintenance"]["recommended_action"], "source": _source("model_derived", "Risque batterie derive du modele maintenance.", "maintenance")},
            {"name": "iot_module", "type": "connectivity", "status": kit["connectivity_status"], "health_score": max(0, 100 - round(float(kit["model_outputs"]["security"]["suspicious_activity_score"]) * 100)), "current_value": latest["signal_strength_dbm"], "unit": "dBm", "risk": kit["model_outputs"]["security"]["risk_level"], "recommendation": kit["model_outputs"]["security"]["recommended_action"], "source": _source("model_derived", "Risque module IoT derive du modele securite.", "security")},
        ],
        "telemetry": {"granularity": "30m", "series": [{"timestamp": record["event_time"], "battery_voltage_v": record["battery_voltage_v"], "solar_power_w": record["solar_power_w"], "battery_temperature_c": record["battery_temperature_c"], "state_of_charge_pct": record["state_of_charge_pct"]} for record in records], "source": _source("telemetry", "Fenetre exacte envoyee aux modeles.")},
        "events": [{"event_id": "evt-kit-001", "type": "score_changed", "timestamp": DEMO_NOW, "severity": kit["risk_level"], "description": "Score de sante actualise depuis les sorties modele.", "source": _source("model_derived", "Evenement derive du score modele.", "LocalInferenceEngine")}],
        "maintenance_prediction": {"failure_probability": kit["model_outputs"]["maintenance"]["technical_risk_probability"], "horizon": "7d", "component": kit["model_outputs"]["maintenance"]["suspected_component"], "confidence": 0.79, "priority": kit["risk_level"], "suggested_action": kit["model_outputs"]["maintenance"]["recommended_action"], "raw_model_output": kit["model_outputs"]["maintenance"], "source": _source("model_output", "Sortie directe infer_maintenance.", "maintenance")},
    }


@app.get(
    "/frontend/fleet",
    summary="Payload frontend de supervision flotte",
    description="Retourne la liste des kits, les filtres disponibles, une pagination demo et des actions frontend.",
)
def frontend_fleet() -> dict:
    demo = _demo_entities()
    kits = demo["kits"]
    return {
        "meta": {
            "schema_version": "fleet.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "La colonne risk_level et model_score vient des predictions. Les positions et statuts connectivite viennent de la telemetrie.",
            "model_runs": demo["model_runs"],
        },
        "summary": {
            "total_kits": len(kits),
            "online": sum(1 for kit in kits if kit["status"] == "operational"),
            "offline": sum(1 for kit in kits if kit["status"] == "offline"),
            "at_risk": sum(1 for kit in kits if kit["risk_level"] != "low"),
            "in_intervention": sum(1 for kit in kits if kit["active_intervention_id"]),
            "anomalies": len(demo["alerts"]),
            "source": _source("mixed", "Statuts depuis telemetrie; risque et anomalies depuis sorties modele.", "LocalInferenceEngine"),
        },
        "kits": kits,
        "pagination": {"page": 1, "page_size": len(kits), "total": len(kits), "total_pages": 1, "next_page": None, "previous_page": None, "sort": "risk_level:desc", "filters": {}},
        "map": {"points": kits, "layers": ["clusters", "heatmap", "risk_zones", "offline_zones"]},
        "location_history": [
            {
                "kit_id": kit_id,
                "points": [
                    {
                        "timestamp": record["event_time"],
                        "latitude": record["latitude"],
                        "longitude": record["longitude"],
                        "speed_mps": record["speed_mps"],
                        "geofence_status": record["geofence_status"],
                    }
                    for record in records
                ],
                "source": _source("telemetry", "Historique GPS issu de la fenetre envoyee au modele."),
            }
            for kit_id, records in demo["windows"].items()
        ],
    }


@app.get(
    "/frontend/customers/{client_id}/risk-profile",
    summary="Payload frontend du profil risque client",
    description="Retourne le profil client de demonstration, le risque paiement non branche, le risque kit et les recommandations.",
)
def frontend_customer_risk_profile(
    client_id: str = Path(
        ...,
        description="Identifiant client lie a un kit dans les donnees de demonstration.",
        examples=["client-001"],
    )
) -> dict:
    demo = _demo_entities()
    customer = next((item for item in demo["customers"] if item["client_id"] == client_id), None)
    if customer is None:
        raise _not_found("client", client_id)
    kit = next(item for item in demo["kits"] if item["client_id"] == client_id)
    records = demo["windows"][kit["kit_id"]]
    latest = records[-1]
    return {
        "meta": {
            "schema_version": "customer-risk.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Il n'existe pas encore de modele client dedie; le risque client est explicitement derive des modeles kit maintenance/securite.",
        },
        "customer": customer,
        "payment_risk": {"score": None, "level": "not_available", "late_payments": None, "amount_due": None, "trend": "not_available", "source": _source("not_available", "Aucun modele paiement ni donnees paiement branchees dans ce MVP.")},
        "consumption": {"average_wh": round(sum(float(record["energy_consumed_wh"]) for record in records) / len(records), 2), "trend": "stable", "anomaly": latest["abnormal_consumption_detected"], "comparison": "calcule uniquement sur la fenetre du kit", "source": _source("telemetry_derived", "Moyenne energy_consumed_wh sur les records du kit.")},
        "kit_risk": {"kit_moved": latest["movement_detected"], "kit_opened": latest["enclosure_opened"], "offline": latest["connection_status"] == "disconnected", "model_score": kit["model_score"], "maintenance_prediction": kit["model_outputs"]["maintenance"], "security_prediction": kit["model_outputs"]["security"], "source": _source("model_output", "Risque client rattache aux predictions du kit.", "LocalInferenceEngine")},
        "recommendations": [{"label": item, "justification": "Action proposee selon le score client et les signaux kit."} for item in customer["recommendations"]],
    }


@app.get(
    "/frontend/performance",
    summary="Payload frontend performance operationnelle et IA",
    description="Retourne indicateurs de performance, modeles, impact financier demo, qualite service et limites connues.",
)
def frontend_performance() -> dict:
    demo = _demo_entities()
    energy_generated = round(sum(float(record.get("energy_generated_wh", 0)) for record in demo["records"]) / 1000, 2)
    open_decisions = sum(1 for decision in demo["decisions"] if decision["status"] == "open")
    model_metadata = engine.metadata
    return {
        "meta": {
            "schema_version": "performance.v1",
            "generated_at": DEMO_NOW,
            "data_mode": "synthetic_demo",
            "ai_traceability": "Les performances modeles viennent de artifacts/metadata.json. Les KPI operationnels disponibles sont derives des predictions et de la telemetrie.",
        },
        "operational_kpis": [
            {**_metric("open_ai_decisions", "Decisions IA ouvertes", open_decisions, "count", 0, "up", "negative", "demo_window"), "source": _source("model_derived", "Compte des decisions ouvertes produites par les modeles.", "LocalInferenceEngine")},
            {**_metric("critical_decisions", "Decisions critiques", sum(1 for decision in demo["decisions"] if decision["severity"] == "critical"), "count", 0, "up", "negative", "demo_window"), "source": _source("model_derived", "Compte des severites issues de la priorisation modele.", "LocalInferenceEngine")},
            {"id": "mttr", "label": "MTTR", "value": None, "unit": "hours", "state": "unknown", "source": _source("not_available", "Pas encore de resultats d'intervention persistants.")},
            {"id": "confirmation_rate", "label": "Taux de confirmation", "value": None, "unit": "percent", "state": "unknown", "source": _source("not_available", "Pas encore de feedback humain persiste.")},
        ],
        "energy_impact": {"generated": {"value": energy_generated, "unit": "kWh"}, "saved": {"value": None, "unit": "kWh"}, "co2_avoided": {"value": round(energy_generated * 0.61, 2), "unit": "kg"}, "method": "Energie generee depuis telemetrie synthetique; CO2 derive par facteur demo; energie sauvee non disponible sans baseline reelle.", "source": _source("telemetry_derived", "Somme energy_generated_wh.")},
        "financial_impact": {"estimated_savings": None, "avoided_losses": None, "roi": None, "methodology": "Non calcule par les modeles actuels. Il faut une table couts/interventions/fraudes confirmees.", "uncertainty": "not_available", "source": _source("not_available", "Aucun modele financier ni donnees couts branchees.")},
        "models": [
            {"name": "maintenance", "version": model_metadata["maintenance"]["model_version"], "accuracy": model_metadata["maintenance"]["accuracy"], "precision": None, "recall": None, "f1": None, "false_positive_rate": None, "training_rows": model_metadata["maintenance"]["training_rows"], "evaluation_period": "synthetic_training_metadata", "health": "demo_only", "features": model_metadata["maintenance"]["features"], "limitations": model_metadata["maintenance"]["limitations"], "source": _source("artifact_metadata", "Metadonnees chargees depuis artifacts/metadata.json.", "maintenance")},
            {"name": "security", "version": model_metadata["security"]["model_version"], "accuracy": model_metadata["security"]["accuracy"], "precision": None, "recall": None, "f1": None, "false_positive_rate": None, "training_rows": model_metadata["security"]["training_rows"], "evaluation_period": "synthetic_training_metadata", "health": "demo_only", "features": model_metadata["security"]["features"], "limitations": model_metadata["security"]["limitations"], "source": _source("artifact_metadata", "Metadonnees chargees depuis artifacts/metadata.json.", "security")},
        ],
        "drift": {"data_drift": "not_available", "feature_drift": "not_available", "prediction_drift": "not_available", "threshold": None, "recommendation": "Ajouter un monitoring MLOps sur donnees reelles avant d'afficher une derive.", "source": _source("not_available", "Les modeles actuels ne calculent pas la derive.")},
    }


@app.get(
    "/frontend/admin/data-ai",
    summary="Payload frontend administration Data et IA",
    description="Retourne metadonnees modeles, contrats de donnees, qualite de donnees et statut des connecteurs futurs.",
)
def frontend_admin_data_ai() -> dict:
    model_metadata = engine.metadata
    return {
        "meta": {"schema_version": "admin-data-ai.v1", "generated_at": DEMO_NOW, "data_mode": "synthetic_demo", "ai_traceability": "Etat technique lu depuis le moteur charge et ses metadonnees locales."},
        "models": [
            {"name": "maintenance", "version": model_metadata["maintenance"]["model_version"], "status": "loaded", "environment": "local", "trained_at": None, "schema_version": "telemetry.v1", "accuracy": model_metadata["maintenance"]["accuracy"], "features": model_metadata["maintenance"]["features"], "source": _source("artifact_metadata", "Modele joblib charge par LocalInferenceEngine.", "maintenance")},
            {"name": "security", "version": model_metadata["security"]["model_version"], "status": "loaded", "environment": "local", "trained_at": None, "schema_version": "telemetry.v1", "accuracy": model_metadata["security"]["accuracy"], "features": model_metadata["security"]["features"], "source": _source("artifact_metadata", "Modele joblib charge par LocalInferenceEngine.", "security")},
        ],
        "pipelines": [{"name": "ingestion", "status": "ok", "last_run_at": DEMO_NOW, "metrics": telemetry_service.metrics.snapshot(), "source": _source("runtime_metrics", "Metriques en memoire de TelemetryIngestionService.")}, {"name": "feature_pipeline", "status": "ok", "last_run_at": DEMO_NOW, "maintenance_features": model_metadata["maintenance"]["features"], "security_features": model_metadata["security"]["features"], "source": _source("artifact_metadata", "Features attendues par les modeles.")}],
        "data_quality": {"completeness_pct": None, "late_data": None, "validation_errors": None, "message": "Qualite globale non calculee ici; consulter /telemetry/quarantine pour les rejets runtime.", "source": _source("not_available", "Pas encore de job data quality global branche a cette route.")},
    }


@app.get(
    "/frontend/realtime/events",
    summary="Payload frontend des evenements temps reel",
    description="Retourne des abonnements et evenements de demonstration pour simuler le flux temps reel cote interface.",
)
def frontend_realtime_events() -> dict:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    demo = _demo_entities()
    first_decision = demo["decisions"][0]
    first_kit = demo["kits"][0]
    return {
        "meta": {"schema_version": "realtime-events.v1", "generated_at": now, "transport": "polling_demo", "upgrade_path": "SSE ou WebSocket", "ai_traceability": "Evenements generes depuis les decisions modele courantes; transport temps reel non encore persistant."},
        "subscriptions": ["global", "region", "kit", "decision", "event_type", "severity"],
        "events": [
            {"event_id": "rt-001", "type": "new_telemetry", "version": 1, "timestamp": now, "entity": {"type": "kit", "id": first_kit["kit_id"]}, "old_values": {}, "new_values": {"connection_status": first_kit["connectivity_status"], "model_score": first_kit["model_score"]}, "severity": first_kit["risk_level"], "source": _source("model_derived", "Evenement derive de la derniere fenetre analysee.", "LocalInferenceEngine"), "correlation_id": "corr-demo-001", "message": "Nouvelle telemetrie analysee par le modele.", "suggested_action": "Actualiser la carte et les alertes."},
            {"event_id": "rt-002", "type": "score_changed", "version": 1, "timestamp": now, "entity": {"type": "decision", "id": first_decision["decision_id"]}, "old_values": {}, "new_values": {"score": first_decision["score"], "maintenance_probability": first_decision["model_outputs"]["maintenance"]["technical_risk_probability"], "security_probability": first_decision["model_outputs"]["security"]["suspicious_activity_score"]}, "severity": first_decision["severity"], "source": _source("model_output", "Score calcule par infer_maintenance et infer_security.", "LocalInferenceEngine"), "correlation_id": "corr-demo-002", "message": "Score IA actualise.", "suggested_action": "Ouvrir la decision."},
        ],
    }


@app.get(
    "/scoring/customers/{phone}",
    summary="Score ML du risque client depuis l'API externe",
    description=(
        "Appelle /api/external/scoring-data/{phone}, transforme le profil client et l'historique "
        "de paiement en features ML, puis retourne un score de risque a 90 jours."
    ),
)
def customer_scoring(
    phone: str = Path(..., description="Numero Orange Money identifiant le client.", examples=["0848451555"]),
    explain_with_llm: bool = Query(
        False,
        description="Si true, demande une explication detaillee a OpenAI. Sinon explication locale deterministe.",
    ),
) -> dict:
    try:
        return _customer_scoring_service().score_from_external_api(phone, explain_with_llm=explain_with_llm)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post(
    "/v1/customer/evaluate",
    summary="Evaluer une decision client multidimensionnelle",
    description=(
        "Consomme un snapshot Backend -> IA deja resolu cote identite et retourne les dimensions "
        "Client Value, Payment Risk, Operational Risk et Intervention Priority."
    ),
)
def customer_decision_evaluate(payload: CustomerDecisionRequest) -> dict:
    # Flux direct: le backend fournit deja kit_intelligence; l'IA calcule et historise la decision client.
    input_snapshot = _customer_decision_snapshot(payload)
    decision = _customer_scoring_service().evaluate_customer_context(input_snapshot)
    return _with_persisted_customer_decision(input_snapshot, decision)


def _evaluate_customer_from_telemetry_payload(payload: CustomerDecisionFromTelemetryRequest) -> dict:
    # Coeur commun: telemetrie backend resolue -> predictions kit -> scoring client -> persistence.
    assembled = _customer_decision_context_from_telemetry(payload)
    decision = _customer_scoring_service().evaluate_customer_context(assembled["context"])
    response = {
        **decision,
        "identity_contract": {
            "status": assembled["identity_status"],
            "source": "backend_payload",
            "resolved_by": "backend",
        },
        "kit_intelligence_source": {
            "kind": "model_output",
            "detail": "maintenance_risk et security_risk calcules depuis records[] par LocalInferenceEngine.",
            "kit_intelligence": assembled["kit_intelligence"],
            "maintenance_prediction": assembled["maintenance_prediction"],
            "security_prediction": assembled["security_prediction"],
        },
        "trend_source": {
            **assembled["storage_summary"],
            "table": "telemetry_records",
            "prediction_history_table": "prediction_history",
            "stored_prediction_id": assembled["stored_prediction"]["prediction_id"],
            "feature_snapshot": assembled["feature_snapshot"],
        },
    }
    return _with_persisted_customer_decision(assembled["context"], response)


def _evaluate_backend_resolved_snapshot(snapshot: dict[str, Any]) -> dict:
    payload = CustomerDecisionFromTelemetryRequest.model_validate(snapshot)
    return _evaluate_customer_from_telemetry_payload(payload)


@app.post(
    "/v1/customer/evaluate-from-telemetry",
    summary="Evaluer une decision client depuis la telemetrie brute",
    description=(
        "Calcule les predictions maintenance/securite depuis records[], construit kit_intelligence, "
        "puis retourne la decision client multidimensionnelle."
    ),
)
def customer_decision_evaluate_from_telemetry(payload: CustomerDecisionFromTelemetryRequest) -> dict:
    # Flux push: le backend appelle directement l'API IA/Data avec un snapshot resolu.
    return _evaluate_customer_from_telemetry_payload(payload)


@app.post(
    "/v1/backend-sync/resolved-telemetry-events/run",
    summary="Consommer les snapshots resolus exposes par le backend metier",
    description=(
        "Flux pull: l'API IA/Data appelle le backend metier, traite chaque item via le meme pipeline que "
        "/v1/customer/evaluate-from-telemetry, puis envoie un ACK technique de traitement."
    ),
)
def backend_resolved_events_sync(payload: BackendResolvedEventsSyncRequest) -> dict:
    client = BackendResolvedEventsClient(
        payload.backend_base_url,
        resolved_events_path=payload.resolved_events_path,
        ack_path_template=payload.ack_path_template,
        timeout_seconds=payload.timeout_seconds,
    )
    return client.process_resolved_events(
        processor=_evaluate_backend_resolved_snapshot,
        cursor=payload.cursor,
        limit=payload.limit,
        ack=payload.ack,
    )


@app.get(
    "/v1/customer/decisions",
    summary="Lister les decisions client historisees",
    description="Retourne l'historique des scorings client stockes pour alimenter le frontend.",
)
def customer_decision_history(
    client_id: Annotated[str | None, Query(description="Filtrer par client_id.")] = None,
    kit_id: Annotated[str | None, Query(description="Filtrer par kit_id.")] = None,
    device_id: Annotated[str | None, Query(description="Filtrer par device_id.")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Nombre maximum de decisions retournees.")] = 50,
) -> dict:
    return {
        "items": realtime_store.list_customer_decisions(
            client_id=client_id,
            kit_id=kit_id,
            device_id=device_id,
            limit=limit,
        )
    }


@app.get(
    "/v1/customer/decisions/{decision_id}",
    summary="Lire le detail d'une decision client",
    description="Retourne le snapshot d'entree et le resultat IA complet pour audit ou affichage frontend.",
)
def customer_decision_detail(
    decision_id: str = Path(..., description="Identifiant retourne par /v1/customer/evaluate*.")
) -> dict:
    decision = realtime_store.get_customer_decision(decision_id)
    if decision is None:
        raise _not_found("decision", decision_id)
    return decision


@app.get(
    "/v1/predictions",
    summary="Lister les predictions techniques historisees",
    description="Retourne les predictions maintenance/securite filtrees par client, kit ou device.",
)
def prediction_history_v1(
    client_id: Annotated[str | None, Query(description="Filtrer par client_id.")] = None,
    kit_id: Annotated[str | None, Query(description="Filtrer par kit_id.")] = None,
    device_id: Annotated[str | None, Query(description="Filtrer par device_id.")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Nombre maximum de predictions retournees.")] = 50,
) -> dict:
    return {
        "items": realtime_store.list_predictions(
            client_id=client_id,
            kit_id=kit_id,
            device_id=device_id,
            limit=limit,
        )
    }


@app.get(
    "/v1/customers",
    summary="Lister les clients connus cote IA",
    description="Retourne la vue locale des clients alimentee par les snapshots recus du backend.",
)
def customer_profiles(
    limit: Annotated[int, Query(ge=1, le=500, description="Nombre maximum de clients retournes.")] = 50,
) -> dict:
    return {"items": realtime_store.list_customers(limit=limit)}


@app.get(
    "/v1/customers/{client_id}",
    summary="Lire la fiche client locale cote IA",
    description="Retourne le dernier snapshot client connu, ses derniers scores et sa derniere decision.",
)
def customer_profile_detail(
    client_id: str = Path(..., description="Identifiant client fourni par le backend metier.")
) -> dict:
    customer = realtime_store.get_customer(client_id)
    if customer is None:
        raise _not_found("client", client_id)
    return customer
