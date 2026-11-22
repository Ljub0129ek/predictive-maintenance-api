"""Pydantic-schemas: formen på data ind og ud af API'et (vises i Swagger)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..domain.model import Alarm
from ..domain.value_objects import Severity


class TelemetryIn(BaseModel):
    """En måling fra en sensor på en vindmølle."""

    asset_id: str = Field(min_length=1, max_length=64, description="Møllens id.", examples=["WTG-001"])
    sensor_type: str = Field(
        min_length=1, max_length=64, description="Sensortype. Kun vibration tjekkes mod grænsen.",
        examples=["vibration"],
    )
    value: float = Field(description="Den målte værdi.", examples=[8.9])
    unit: str = Field(min_length=1, max_length=16, description="Enhed, fx mm/s.", examples=["mm/s"])


class AlarmOut(BaseModel):
    alarm_id: str
    asset_id: str
    severity: Severity
    message: str
    status: str
    created_at: datetime
    caused_by_event_id: str

    @classmethod
    def from_domain(cls, alarm: Alarm) -> "AlarmOut":
        return cls(**vars(alarm))


class EventOut(BaseModel):
    event_id: str
    event_type: str
    asset_id: str
    occurred_at: datetime
    payload: dict[str, Any]


class TelemetryOut(BaseModel):
    status: str
    asset_id: str
    anomaly_detected: bool = Field(description="True, hvis værdien var over grænsen.")
    is_flagged_for_maintenance: bool = Field(description="True, hvis møllen skal til vedligehold.")
    events: list[EventOut]
    alarms: list[AlarmOut]
