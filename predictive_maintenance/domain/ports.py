"""Port: domænets kontrakt for lagring. Adapters i infrastructure/ opfylder den."""

from typing import Protocol

from .events import DomainEvent
from .model import Alarm, Asset


class AssetRepository(Protocol):
    def get(self, asset_id: str) -> Asset | None: ...

    def save(self, asset: Asset, events: list[DomainEvent], alarms: list[Alarm]) -> None:
        """Gemmer assetets tilstand, dets events og nye alarmer samlet."""
        ...

    def list_alarms(self, asset_id: str | None = None) -> list[Alarm]: ...

    def list_events(self, asset_id: str | None = None) -> list[dict]: ...

    def ping(self) -> bool: ...
