"""Domænehændelser fra Event Storming i Delopgave 1 (navngivet i datid)."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from .value_objects import Severity


def _new_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class SensorTelemetryReceived:
    """Kildehændelse: en sensorværdi er modtaget fra et asset."""

    asset_id: str
    sensor_type: str
    value: float
    unit: str
    occurred_at: datetime
    event_id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class AnomalyDetected:
    """Domænehændelse: en måling overskred grænseværdien."""

    asset_id: str
    sensor_type: str
    measured_value: float
    threshold_value: float
    severity: Severity
    occurred_at: datetime
    event_id: str = field(default_factory=_new_id)


DomainEvent = SensorTelemetryReceived | AnomalyDetected
