"""Omsætter domænehændelser til en form, der kan gemmes (type + JSON-data)."""

from dataclasses import asdict
from datetime import datetime
from enum import Enum

from ..domain.events import DomainEvent


def event_to_record(event: DomainEvent) -> dict:
    payload = {}
    for key, value in asdict(event).items():
        if key in ("event_id", "occurred_at", "asset_id"):
            continue
        if isinstance(value, Enum):
            value = value.value
        elif isinstance(value, datetime):
            value = value.isoformat()
        payload[key] = value
    return {
        "event_id": event.event_id,
        "event_type": type(event).__name__,
        "asset_id": event.asset_id,
        "occurred_at": event.occurred_at,
        "payload": payload,
    }
