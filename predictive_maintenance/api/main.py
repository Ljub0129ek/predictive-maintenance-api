"""FastAPI: inbound adapter, der oversætter HTTP-kald til kald på applikationslaget."""

import logging
import os
import secrets
import time
from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.security import APIKeyHeader

from ..application.services import AssetNotFound, handle_telemetry
from ..domain.model import Asset
from ..domain.ports import AssetRepository
from ..infrastructure.serialization import event_to_record
from . import metrics
from .rate_limit import RateLimiter
from .schemas import AlarmOut, EventOut, TelemetryIn, TelemetryOut


def build_repository() -> AssetRepository:
    """Vælger lagring ud fra miljøvariablen REPOSITORY (mysql eller memory)."""
    if os.getenv("REPOSITORY", "memory").lower() == "mysql":
        from ..infrastructure.mysql_repository import MySQLAssetRepository

        return MySQLAssetRepository(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
    from ..infrastructure.memory_repository import InMemoryAssetRepository

    return InMemoryAssetRepository(assets=[Asset("WTG-001")])


TAGS = [
    {"name": "telemetry", "description": "Modtag sensorværdier fra vindmøller (SensorTelemetryReceived)."},
    {"name": "alarms", "description": "Alarmer, som kontrolcentret skal reagere på."},
    {"name": "events", "description": "Domænehændelser fra Event Storming i Delopgave 1."},
    {"name": "drift", "description": "Tjek om API og database kører."},
]

TELEMETRY_EXAMPLES = {
    "normal": {
        "summary": "1 Normal værdi 4.0 (ingen alarm)",
        "description": "Under grænsen 7,5 mm/s. Giver kun SensorTelemetryReceived.",
        "value": {"asset_id": "WTG-001", "sensor_type": "vibration", "value": 4.0, "unit": "mm/s"},
    },
    "warning": {
        "summary": "2 Høj værdi 8.9 (WARNING-alarm)",
        "description": "Over grænsen 7,5 mm/s. Giver AnomalyDetected og en WARNING-alarm.",
        "value": {"asset_id": "WTG-001", "sensor_type": "vibration", "value": 8.9, "unit": "mm/s"},
    },
    "critical": {
        "summary": "3 Kritisk værdi 12.0 (CRITICAL-alarm)",
        "description": "Over 1,5 x grænsen (11,25 mm/s). Giver en CRITICAL-alarm.",
        "value": {"asset_id": "WTG-001", "sensor_type": "vibration", "value": 12.0, "unit": "mm/s"},
    },
    "unknown": {
        "summary": "4 Ukendt mølle (fejl 404)",
        "description": "WTG-999 findes ikke, så API'et svarer 404.",
        "value": {"asset_id": "WTG-999", "sensor_type": "vibration", "value": 8.9, "unit": "mm/s"},
    },
}

# Audit-log: hvem kaldte hvad, hvornår og med hvilket resultat (Hands-on 3)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
audit_log = logging.getLogger("audit")
audit_log.setLevel(logging.INFO)


def configure_audit_file(path: str | None) -> None:
    """Skriver også audit-loggen til en fil, hvis AUDIT_LOG_FILE er sat."""
    if not path:
        return
    if any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(path)
           for h in audit_log.handlers):
        return  # Allerede sat op
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    audit_log.addHandler(handler)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "ukendt"


API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API-nøglen fra filen .env. Kræves for at sende sensorværdier.",
)

ASSET_FILTER = Query(None, description="Vis kun for ét asset, fx WTG-001.", examples=["WTG-001"])


def create_app(
    repository: AssetRepository | None = None,
    api_key: str | None = None,
    rate_limit_per_minute: int = 20,
) -> FastAPI:
    app = FastAPI(
        title="Predictive Maintenance API",
        version="1.0.0",
        description=(
            "Teknisk MVP for Intelligent IoT Solutions A/S.\n\n"
            "Flowet fra Event Storming: **SensorTelemetryReceived -> threshold-check -> "
            "AnomalyDetected -> Alarm**.\n\n"
            "Grænsen for vibration er 7,5 mm/s. Over grænsen = WARNING, over 1,5 x grænsen = CRITICAL."
        ),
        openapi_tags=TAGS,
        # Skjul den tekniske Schemas-sektion nederst i Swagger (findes stadig under hvert endpoint)
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    app.state.repository = repository or build_repository()

    app.state.api_key = api_key if api_key is not None else os.getenv("API_KEY", "")

    configure_audit_file(os.getenv("AUDIT_LOG_FILE"))
    app.state.rate_limiter = RateLimiter(max_calls=rate_limit_per_minute, window_seconds=60)

    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        """Logger hvert kald. API-nøglen og kroppen logges aldrig."""
        start = time.perf_counter()
        response = await call_next(request)
        seconds = time.perf_counter() - start
        ms = seconds * 1000
        # Brug rute-skabelonen (fx /api/v1/alarms), så ukendte stier ikke giver mange tællere
        route = request.scope.get("route")
        path = route.path if route is not None else "ukendt"
        metrics.HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        metrics.HTTP_LATENCY.labels(request.method, path).observe(seconds)
        if path == "/health" and client_ip(request) == "127.0.0.1":
            return response  # Dockers egen healthcheck hvert 15. sekund fylder ikke audit-loggen
        audit_log.info(
            "ip=%s method=%s path=%s status=%s ms=%.1f",
            client_ip(request), request.method, request.url.path, response.status_code, ms,
        )
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        """Fælles fejlhåndtering: detaljerne logges, klienten får en generisk besked."""
        audit_log.exception("Uventet fejl: method=%s path=%s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Der skete en intern fejl. Prøv igen senere."})

    def get_repo(request: Request) -> AssetRepository:
        return request.app.state.repository

    def rate_limit(request: Request) -> None:
        """Højst 20 kald i minuttet pr. IP. Tæller også kald med forkert nøgle."""
        ip = client_ip(request)
        if not request.app.state.rate_limiter.allow(ip):
            audit_log.warning("Rate limit overskredet: ip=%s path=%s", ip, request.url.path)
            raise HTTPException(
                status_code=429,
                detail="For mange kald. Prøv igen om et minut.",
                headers={"Retry-After": "60"},
            )

    def require_api_key(request: Request, key: str | None = Depends(API_KEY_HEADER)) -> None:
        """Kun klienter med den rigtige nøgle må sende sensorværdier."""
        expected = request.app.state.api_key
        if not expected:
            # Sikker standard: uden en nøgle sat op afvises alle kald
            raise HTTPException(status_code=503, detail="API-nøglen er ikke sat op på serveren.")
        if not key or not secrets.compare_digest(key, expected):
            audit_log.warning(
                "Afvist API-nøgle: ip=%s path=%s grund=%s",
                client_ip(request), request.url.path, "mangler" if not key else "forkert",
            )
            raise HTTPException(status_code=401, detail="Manglende eller forkert API-nøgle.")

    @app.post(
        "/api/v1/telemetry",
        response_model=TelemetryOut,
        tags=["telemetry"],
        summary="Send en sensorværdi",
        description=(
            "Modtager én måling fra en vindmølle. Er vibrationen over grænsen, "
            "registreres AnomalyDetected, der oprettes en alarm, og møllen markeres til vedligehold. "
            "Kræver API-nøgle (angives under Authorize øverst). Højst 20 kald i minuttet. Eksempler kan vælges i listen nedenfor."
        ),
        responses={
            401: {"description": "Manglende eller forkert API-nøgle."},
            404: {"description": "Asset ikke fundet."},
            422: {"description": "Ugyldigt input, fx vibration under 0 eller over 100."},
            429: {"description": "For mange kald (højst 20 i minuttet)."},
        },
        dependencies=[Depends(rate_limit), Depends(require_api_key)],
    )
    def post_telemetry(
        body: Annotated[TelemetryIn, Body(openapi_examples=TELEMETRY_EXAMPLES)],
        repo: AssetRepository = Depends(get_repo),
    ):
        try:
            result = handle_telemetry(repo, body.asset_id, body.sensor_type, body.value, body.unit)
        except AssetNotFound:
            raise HTTPException(status_code=404, detail="Asset ikke fundet.")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        metrics.TELEMETRY_RECEIVED.labels(body.sensor_type).inc()
        for alarm in result.alarms:
            metrics.ANOMALIES_DETECTED.labels(alarm.severity.value).inc()
        return TelemetryOut(
            status="PROCESSED",
            asset_id=result.asset.asset_id,
            anomaly_detected=bool(result.alarms),
            is_flagged_for_maintenance=result.asset.is_flagged_for_maintenance,
            events=[EventOut(**event_to_record(e)) for e in result.events],
            alarms=[AlarmOut.from_domain(a) for a in result.alarms],
        )

    @app.get(
        "/api/v1/alarms",
        response_model=list[AlarmOut],
        tags=["alarms"],
        summary="Se alarmer",
        description="Viser alarmer gemt i databasen, ældste først.",
    )
    def get_alarms(asset_id: str | None = ASSET_FILTER, repo: AssetRepository = Depends(get_repo)):
        return [AlarmOut.from_domain(a) for a in repo.list_alarms(asset_id)]

    @app.get(
        "/api/v1/events",
        response_model=list[EventOut],
        tags=["events"],
        summary="Se domænehændelser",
        description="Viser SensorTelemetryReceived og AnomalyDetected i den rækkefølge, de skete.",
    )
    def get_events(asset_id: str | None = ASSET_FILTER, repo: AssetRepository = Depends(get_repo)):
        return [EventOut(**e) for e in repo.list_events(asset_id)]

    @app.get(
        "/health",
        tags=["drift"],
        summary="Sundhedstjek",
        description="Svarer 200, hvis API og database kører, ellers 503.",
    )
    def health(repo: AssetRepository = Depends(get_repo)):
        if not repo.ping():
            return JSONResponse(status_code=503, content={"status": "error", "database": "down"})
        return {"status": "ok", "database": "up"}

    @app.get(
        "/metrics",
        tags=["drift"],
        summary="Metrics til overvågning",
        description="Tællere og svartider i Prometheus-format, fx antal målinger, anomalier og fejl.",
        response_class=Response,
    )
    def get_metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
