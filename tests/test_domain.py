"""Enhedstest af domænereglerne (kører uden database og uden web)."""

from datetime import UTC, datetime

import pytest

from predictive_maintenance.domain.events import AnomalyDetected, SensorTelemetryReceived
from predictive_maintenance.domain.model import Alarm, Asset
from predictive_maintenance.domain.value_objects import SensorReading, Severity, VibrationThreshold

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)


def reading(value: float, sensor_type: str = "vibration") -> SensorReading:
    return SensorReading(sensor_type=sensor_type, value=value, unit="mm/s", measured_at=NOW)


def test_normal_value_gives_only_telemetry_event():
    asset = Asset("WTG-001")
    events = asset.record_telemetry(reading(4.0))
    assert [type(e) for e in events] == [SensorTelemetryReceived]
    assert asset.is_flagged_for_maintenance is False


def test_value_exactly_at_threshold_is_not_an_anomaly():
    events = Asset("WTG-001").record_telemetry(reading(7.5))
    assert not any(isinstance(e, AnomalyDetected) for e in events)


def test_value_over_threshold_gives_warning_anomaly():
    asset = Asset("WTG-001")
    events = asset.record_telemetry(reading(8.9))
    anomaly = events[-1]
    assert isinstance(anomaly, AnomalyDetected)
    assert anomaly.severity == Severity.WARNING
    assert anomaly.threshold_value == 7.5
    assert asset.is_flagged_for_maintenance is True


def test_value_over_one_and_a_half_times_threshold_is_critical():
    events = Asset("WTG-001").record_telemetry(reading(12.0))
    assert events[-1].severity == Severity.CRITICAL


def test_other_sensor_types_do_not_trigger_vibration_rule():
    events = Asset("WTG-001").record_telemetry(reading(99.0, sensor_type="bearing_temp"))
    assert len(events) == 1


def test_alarm_is_created_from_anomaly():
    anomaly = Asset("WTG-001").record_telemetry(reading(8.9))[-1]
    alarm = Alarm.from_anomaly(anomaly)
    assert alarm.status == "OPEN"
    assert alarm.severity == Severity.WARNING
    assert alarm.caused_by_event_id == anomaly.event_id


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sensor_type": "", "value": 1.0, "unit": "mm/s"},
        {"sensor_type": "vibration", "value": 1.0, "unit": ""},
        {"sensor_type": "vibration", "value": -1.0, "unit": "mm/s"},
        {"sensor_type": "vibration", "value": float("nan"), "unit": "mm/s"},
    ],
)
def test_invalid_readings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        SensorReading(measured_at=NOW, **kwargs)


def test_reading_requires_timezone():
    with pytest.raises(ValueError):
        SensorReading("vibration", 1.0, "mm/s", datetime(2026, 1, 1))


def test_threshold_must_be_positive():
    with pytest.raises(ValueError):
        VibrationThreshold(limit=0)
