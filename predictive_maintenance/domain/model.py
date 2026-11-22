"""Aggregate Root (Asset) og entiteten Alarm."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from .events import AnomalyDetected, DomainEvent, SensorTelemetryReceived
from .value_objects import SensorReading, Severity, VibrationThreshold


@dataclass
class Alarm:
    """Handlingen i flowet: en alarm, som kontrolcentret skal reagere på."""

    asset_id: str
    severity: Severity
    message: str
    created_at: datetime
    caused_by_event_id: str
    status: str = "OPEN"
    alarm_id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def from_anomaly(cls, event: AnomalyDetected) -> "Alarm":
        return cls(
            asset_id=event.asset_id,
            severity=event.severity,
            message=(
                f"{event.sensor_type} {event.measured_value} over grænsen "
                f"{event.threshold_value} på {event.asset_id}"
            ),
            created_at=event.occurred_at,
            caused_by_event_id=event.event_id,
        )


class Asset:
    """Et overvåget asset, fx en vindmølle. Konsistensgrænsen for tærskelreglen."""

    def __init__(
        self,
        asset_id: str,
        threshold: VibrationThreshold | None = None,
        is_flagged_for_maintenance: bool = False,
    ) -> None:
        if not asset_id.strip():
            raise ValueError("asset_id må ikke være tom.")
        self.asset_id = asset_id
        self.threshold = threshold or VibrationThreshold()
        self.is_flagged_for_maintenance = is_flagged_for_maintenance

    def record_telemetry(self, reading: SensorReading) -> list[DomainEvent]:
        """Sensorværdi modtaget -> threshold-check -> evt. AnomalyDetected."""
        events: list[DomainEvent] = [
            SensorTelemetryReceived(
                asset_id=self.asset_id,
                sensor_type=reading.sensor_type,
                value=reading.value,
                unit=reading.unit,
                occurred_at=reading.measured_at,
            )
        ]
        if reading.sensor_type == "vibration" and self.threshold.is_exceeded_by(reading.value):
            self.is_flagged_for_maintenance = True
            events.append(
                AnomalyDetected(
                    asset_id=self.asset_id,
                    sensor_type=reading.sensor_type,
                    measured_value=reading.value,
                    threshold_value=self.threshold.limit,
                    severity=self.threshold.severity_for(reading.value),
                    occurred_at=reading.measured_at,
                )
            )
        return events
