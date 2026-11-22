"""MySQL adapter: gemmer assets, domænehændelser og alarmer permanent i MySQL.

Al SQL er parametriseret (%s), så input aldrig sættes direkte ind i SQL-teksten.
Tabellerne oprettes af mysql-init/init.sql, når databasecontaineren starter første gang.
"""

import json
from datetime import UTC, datetime

import mysql.connector

from ..domain.events import DomainEvent
from ..domain.model import Alarm, Asset
from ..domain.value_objects import Severity, VibrationThreshold
from .serialization import event_to_record


def _to_db_time(value: datetime) -> datetime:
    # MySQL DATETIME har ingen tidszone, så vi gemmer altid UTC.
    return value.astimezone(UTC).replace(tzinfo=None)


def _from_db_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)


class MySQLAssetRepository:
    def __init__(self, host: str, port: int, database: str, user: str, password: str) -> None:
        self._config = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }

    def _connect(self):
        return mysql.connector.connect(**self._config)

    def get(self, asset_id: str) -> Asset | None:
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT asset_id, vibration_threshold, is_flagged_for_maintenance "
                "FROM assets WHERE asset_id = %s",
                (asset_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return Asset(
            asset_id=row["asset_id"],
            threshold=VibrationThreshold(limit=float(row["vibration_threshold"])),
            is_flagged_for_maintenance=bool(row["is_flagged_for_maintenance"]),
        )

    def save(self, asset: Asset, events: list[DomainEvent], alarms: list[Alarm]) -> None:
        conn = self._connect()
        try:
            conn.start_transaction()  # Alt eller intet bliver gemt
            cur = conn.cursor()
            cur.execute(
                "UPDATE assets SET is_flagged_for_maintenance = %s WHERE asset_id = %s",
                (asset.is_flagged_for_maintenance, asset.asset_id),
            )
            for event in events:
                rec = event_to_record(event)
                cur.execute(
                    "INSERT INTO domain_events (event_id, event_type, asset_id, occurred_at, payload) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        rec["event_id"],
                        rec["event_type"],
                        rec["asset_id"],
                        _to_db_time(rec["occurred_at"]),
                        json.dumps(rec["payload"]),
                    ),
                )
            for alarm in alarms:
                cur.execute(
                    "INSERT INTO alarms (alarm_id, asset_id, severity, message, status, "
                    "created_at, caused_by_event_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        alarm.alarm_id,
                        alarm.asset_id,
                        alarm.severity.value,
                        alarm.message,
                        alarm.status,
                        _to_db_time(alarm.created_at),
                        alarm.caused_by_event_id,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def list_alarms(self, asset_id: str | None = None) -> list[Alarm]:
        sql = (
            "SELECT alarm_id, asset_id, severity, message, status, created_at, caused_by_event_id "
            "FROM alarms"
        )
        params: tuple = ()
        if asset_id is not None:
            sql += " WHERE asset_id = %s"
            params = (asset_id,)
        sql += " ORDER BY created_at"
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            conn.close()
        return [
            Alarm(
                alarm_id=r["alarm_id"],
                asset_id=r["asset_id"],
                severity=Severity(r["severity"]),
                message=r["message"],
                status=r["status"],
                created_at=_from_db_time(r["created_at"]),
                caused_by_event_id=r["caused_by_event_id"],
            )
            for r in rows
        ]

    def list_events(self, asset_id: str | None = None) -> list[dict]:
        sql = "SELECT event_id, event_type, asset_id, occurred_at, payload FROM domain_events"
        params: tuple = ()
        if asset_id is not None:
            sql += " WHERE asset_id = %s"
            params = (asset_id,)
        sql += " ORDER BY occurred_at"
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            rows = cur.fetchall()
        finally:
            conn.close()
        for r in rows:
            r["occurred_at"] = _from_db_time(r["occurred_at"])
            r["payload"] = json.loads(r["payload"])
        return rows

    def ping(self) -> bool:
        try:
            conn = self._connect()
            conn.close()
            return True
        except mysql.connector.Error:
            return False
