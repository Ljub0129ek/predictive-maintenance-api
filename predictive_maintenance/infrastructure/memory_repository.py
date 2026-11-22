"""In-memory adapter: gemmer alt i hukommelsen. Bruges i tests og til hurtig afprøvning."""

from copy import deepcopy

from ..domain.events import DomainEvent
from ..domain.model import Alarm, Asset
from .serialization import event_to_record


class InMemoryAssetRepository:
    def __init__(self, assets: list[Asset] | None = None) -> None:
        self._assets = {a.asset_id: deepcopy(a) for a in (assets or [])}
        self._events: list[dict] = []
        self._alarms: list[Alarm] = []

    def get(self, asset_id: str) -> Asset | None:
        asset = self._assets.get(asset_id)
        return deepcopy(asset) if asset else None

    def save(self, asset: Asset, events: list[DomainEvent], alarms: list[Alarm]) -> None:
        self._assets[asset.asset_id] = deepcopy(asset)
        self._events.extend(event_to_record(e) for e in events)
        self._alarms.extend(deepcopy(alarms))

    def list_alarms(self, asset_id: str | None = None) -> list[Alarm]:
        return [a for a in self._alarms if asset_id is None or a.asset_id == asset_id]

    def list_events(self, asset_id: str | None = None) -> list[dict]:
        return [e for e in self._events if asset_id is None or e["asset_id"] == asset_id]

    def ping(self) -> bool:
        return True
