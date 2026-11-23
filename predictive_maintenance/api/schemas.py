"""Pydantic-schemas: formen på data ind og ud af API'et (vises i Swagger)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..domain.model import Alarm
from ..domain.value_objects import Severity


class TelemetryIn(BaseModel):
    """En måling fra en sensor på en vindmølle."""

    asset_id: str = Field(min_length=1, max_length=64, description="Møllens id.", examples=["WTG-001"])
    sensor_type: Literal["vibration"] = Field(
        description="Sensortype. MVP'en understøtter kun vibration. Andre typer giver 422.",
        examples=["vibration"],
    )
    value: float = Field(
        ge=0,
        le=100,
        description="Den målte værdi, 0 til 100 (mm/s). Uden for det giver 422.",
        examples=[8.9],
    )
    unit: str = Field(min_length=1, max_length=16, description="Enhed, fx mm/s.", examples=["mm/s"])


# Eksempler, som Swagger viser i stedet for "string"
ALARM_ID = "dc5353bd-e3f1-4929-9c95-645cb7e150e3"
EVENT_ID = "3984b118-2bac-41da-8746-0920bfc61f1d"
TIME = "2026-11-22T19:54:06.967310Z"


class AlarmOut(BaseModel):
    alarm_id: str = Field(examples=[ALARM_ID])
    asset_id: str = Field(examples=["WTG-001"])
    severity: Severity = Field(description="WARNING eller CRITICAL.", examples=["WARNING"])
    message: str = Field(examples=["vibration 8.9 over grænsen 7.5 på WTG-001"])
    status: str = Field(examples=["OPEN"])
    created_at: datetime = Field(examples=[TIME])
    caused_by_event_id: str = Field(description="Den AnomalyDetected, der udløste alarmen.", examples=[EVENT_ID])

    @classmethod
    def from_domain(cls, alarm: Alarm) -> "AlarmOut":
        return cls(**vars(alarm))


class EventOut(BaseModel):
    event_id: str = Field(examples=[EVENT_ID])
    event_type: str = Field(
        description="SensorTelemetryReceived eller AnomalyDetected.", examples=["AnomalyDetected"]
    )
    asset_id: str = Field(examples=["WTG-001"])
    occurred_at: datetime = Field(examples=[TIME])
    payload: dict[str, Any] = Field(
        examples=[
            {"sensor_type": "vibration", "measured_value": 8.9, "threshold_value": 7.5, "severity": "WARNING"}
        ]
    )


class TelemetryOut(BaseModel):
    status: str = Field(examples=["PROCESSED"])
    asset_id: str = Field(examples=["WTG-001"])
    anomaly_detected: bool = Field(description="True, hvis værdien var over grænsen.", examples=[True])
    is_flagged_for_maintenance: bool = Field(
        description="True, hvis møllen skal til vedligehold.", examples=[True]
    )
    events: list[EventOut]
    alarms: list[AlarmOut]
