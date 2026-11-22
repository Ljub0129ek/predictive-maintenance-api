"""Applikationslaget: styrer flowet event -> beslutning -> handling."""

from dataclasses import dataclass
from datetime import UTC, datetime

from ..domain.events import AnomalyDetected, DomainEvent
from ..domain.model import Alarm, Asset
from ..domain.ports import AssetRepository
from ..domain.value_objects import SensorReading


class AssetNotFound(Exception):
    pass


@dataclass
class TelemetryResult:
    asset: Asset
    events: list[DomainEvent]
    alarms: list[Alarm]


def handle_telemetry(
    repo: AssetRepository,
    asset_id: str,
    sensor_type: str,
    value: float,
    unit: str,
    measured_at: datetime | None = None,
) -> TelemetryResult:
    asset = repo.get(asset_id)
    if asset is None:
        raise AssetNotFound(asset_id)

    reading = SensorReading(
        sensor_type=sensor_type,
        value=value,
        unit=unit,
        measured_at=measured_at or datetime.now(UTC),
    )
    events = asset.record_telemetry(reading)  # Beslutningen sker i domænet
    alarms = [Alarm.from_anomaly(e) for e in events if isinstance(e, AnomalyDetected)]
    repo.save(asset, events, alarms)  # Handling: gem events og alarmer
    return TelemetryResult(asset=asset, events=events, alarms=alarms)
