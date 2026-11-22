"""Value Objects: uforanderlige objekter, der kun defineres af deres værdier.

Domænelaget kender ikke til FastAPI, MySQL eller Azure.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class SensorReading:
    """Én måling fra en sensor på et asset (fx en vindmølle)."""

    sensor_type: str  # fx "vibration"
    value: float
    unit: str  # fx "mm/s"
    measured_at: datetime

    def __post_init__(self) -> None:
        if not self.sensor_type.strip():
            raise ValueError("sensor_type må ikke være tom.")
        if not self.unit.strip():
            raise ValueError("unit må ikke være tom.")
        if not math.isfinite(self.value):
            raise ValueError("value skal være et gyldigt tal.")
        if self.measured_at.tzinfo is None:
            raise ValueError("measured_at skal have en tidszone (UTC).")
        if self.sensor_type == "vibration" and self.value < 0:
            raise ValueError("Vibration kan ikke være negativ.")


@dataclass(frozen=True)
class VibrationThreshold:
    """Forretningsregel: over grænsen = WARNING, over 1,5 x grænsen = CRITICAL."""

    limit: float = 7.5
    critical_factor: float = 1.5

    def __post_init__(self) -> None:
        if not math.isfinite(self.limit) or self.limit <= 0:
            raise ValueError("Grænseværdien skal være et positivt tal.")
        if self.critical_factor <= 1:
            raise ValueError("critical_factor skal være større end 1.")

    def is_exceeded_by(self, value: float) -> bool:
        return value > self.limit

    def severity_for(self, value: float) -> Severity:
        if value > self.limit * self.critical_factor:
            return Severity.CRITICAL
        return Severity.WARNING
