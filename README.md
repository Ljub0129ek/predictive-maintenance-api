# Predictive Maintenance API

Teknisk MVP for casen **Intelligent IoT Solutions A/S** (Delopgave 2, fag 6.2).

API'et modtager sensorværdier fra vindmøller og følger flowet fra Event Storming i Delopgave 1:

```
SensorTelemetryReceived  ->  threshold-check  ->  AnomalyDetected  ->  Alarm
```

Er vibrationen over grænsen (7,5 mm/s), oprettes en alarm, og møllen markeres til vedligehold.
Over 1,5 x grænsen bliver alarmen `CRITICAL`, ellers `WARNING`.

Bygget med **FastAPI** og **MySQL** efter hexagonal arkitektur og taktisk DDD:
domænet kender ikke til FastAPI eller MySQL.


## Mappeoversigt

```
predictive_maintenance/domain/model.py            Asset (aggregate root) og Alarm
predictive_maintenance/domain/value_objects.py    SensorReading, VibrationThreshold, Severity
predictive_maintenance/domain/events.py           SensorTelemetryReceived, AnomalyDetected
predictive_maintenance/domain/ports.py            AssetRepository (port)
predictive_maintenance/application/services.py    Use case: handle_telemetry
predictive_maintenance/api/                        FastAPI (inbound adapter) og schemas
predictive_maintenance/infrastructure/             MySQL- og in-memory-lagring (outbound adapters)
mysql-init/init.sql                                Tabeller og testdata (WTG-001)
tests/                                             Domæne- og API-tests
docker-compose.yml, Dockerfile                     Kør API + MySQL i Docker
.github/workflows/ci.yml                           CI: tests, sikkerhedsscans, Docker-build og push til ghcr.io
postman/                                           Postman-samling med testtrin
```


## Kør med Docker (anbefalet)

Kræver Docker Desktop.

```bash
cp .env.example .env          # udfyld egne adgangskoder i .env
docker compose up --build
```

Swagger (interaktiv dokumentation): http://localhost:8000/docs

### Se databasen i MySQL Workbench

MySQL er kun tilgængelig lokalt på `127.0.0.1:3307` og ikke fra netværket.
Forbindelse i Workbench: Hostname `127.0.0.1`, Port `3307`, Username og Password
fra `DB_USER` og `DB_PASSWORD` i `.env`. Eksempel på forespørgsel:
`SELECT * FROM predictive_maintenance.alarms;`

Løsningen stoppes med `Ctrl+C` eller `docker compose down`.
Data i MySQL bliver gemt mellem genstarter. `docker compose down -v` sletter dem.


## Kør tests (uden Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

Testene bruger in-memory-lagring, så MySQL er ikke nødvendig.


## Endpoints

```
POST  /api/v1/telemetry           Send en sensorværdi (kræver API-nøgle)
GET   /api/v1/alarms?asset_id=    Se alarmer (evt. for ét asset)
GET   /api/v1/events?asset_id=    Se domænehændelser
GET   /health                     Kører API'et, og svarer databasen?
GET   /metrics                    Tællere og svartider (Prometheus-format)
```

Eksempel:

```bash
curl -X POST http://localhost:8000/api/v1/telemetry \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY fra .env>" \
  -d '{"asset_id": "WTG-001", "sensor_type": "vibration", "value": 8.9, "unit": "mm/s"}'
```

| Værdi (mm/s) | Resultat               |
|--------------|------------------------|
| 4.0          | Ingen alarm            |
| 8.9          | Alarm, `WARNING`       |
| 12.0         | Alarm, `CRITICAL`      |


## Postman

Samlingen `postman/predictive-maintenance.postman_collection.json` importeres i Postman
(Import). Trinene køres i rækkefølge, eller hele samlingen på én gang med **Run**:

```
0 Health          1 Normal værdi 4.0    2 Høj værdi 8.9     3 Se alarmer
4 Kritisk 12.0    5 Se hændelser        6 Ukendt mølle (404)  7 Uden API-nøgle (401)
8 Ugyldig værdi -5 (422)
```

Variablen `api_key` (samlingen -> fanen Variables) skal sættes til `API_KEY` fra `.env`.
Hvert trin har små tests, der viser grønt, når svaret er som forventet.
I Swagger (http://localhost:8000/docs) angives nøglen under **Authorize**. Derefter kan de samme eksempler vælges i en liste under `POST /api/v1/telemetry`.
Nulstilling til tom database: `docker compose down -v && docker compose up -d`.


## Drift og overvågning

- **Healthcheck:** Docker kalder selv `/health` hvert 15. sekund. `docker compose ps` viser `healthy`,
  og containeren genstartes, hvis den går ned.
- **Metrics:** `GET /metrics` viser bl.a. `telemetry_received_total`, `anomalies_detected_total`,
  `http_requests_total` (pr. status) og `http_request_duration_seconds` (svartid). Kan bruges til SLI/SLO,
  fx andel fejl og svartid.
- **Container-image:** ved hvert push til `main` lægger CI imaget på GitHub Container Registry
  (`ghcr.io/ljub0129ek/predictive-maintenance-api`), men kun når tests og sikkerhedsscan er grønne.


## Sikkerhed

- `POST /api/v1/telemetry` kræver en API-nøgle i headeren `X-API-Key`, så kun godkendte sensorer kan sende data.
  Mangler nøglen eller er den forkert, svarer API'et 401. Er der ingen nøgle sat op på serveren, afvises alle kald (sikker standard).
  Læse-endpoints og `/health` er åbne i denne MVP.
- **Rate limiting:** højst 20 kald i minuttet pr. IP-adresse på `POST /api/v1/telemetry`. Ellers svarer API'et 429.
  Kald med forkert nøgle tæller med, så man ikke kan gætte nøglen ved at prøve mange gange.
- **Audit-log:** hvert kald logges (IP, metode, sti, status, tid). Afviste nøgler og rate limiting logges som `WARNING`.
  API-nøglen og indholdet af kaldet logges aldrig. Loggen skrives til `logs/audit.log` (versionsstyres ikke)
  og kan også ses med `docker compose logs -f api`.
- **Fælles fejlhåndtering:** uventede fejl giver 500 med en generisk besked. Detaljerne står kun i loggen.

- Adgangskoder ligger i `.env`, som er udelukket fra versionsstyring (`.gitignore`).
- Al SQL er parametriseret, så input ikke kan ændre SQL-sætningen.
- Input valideres af Pydantic (kun `sensor_type` "vibration", værdi 0 til 100 mm/s, ellers 422) og af domænets value objects.
- API-containeren kører ikke som root.
- CI kører to sikkerhedsscans ved hvert push (DevSecOps):
  - **Bandit** scanner koden for usikre mønstre, fx SQL-injection og hårdkodede adgangskoder.
  - **pip-audit** tjekker pakkerne i `requirements.txt` mod kendte sikkerhedshuller.
  Docker-imaget bygges kun, hvis både tests og scans er grønne.

Scans kan også køres lokalt:

```bash
pip install bandit==1.8.6 pip-audit==2.9.0
bandit -r predictive_maintenance
pip-audit -r requirements.txt
```
