"""Metrics til overvågning (Prometheus-format), fx til SLI/SLO.

Tællerne ligger i hukommelsen og nulstilles, når containeren genstarter.
"""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Antal HTTP-kald fordelt på metode, sti og status.",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Svartid for HTTP-kald i sekunder.",
    ["method", "path"],
)
TELEMETRY_RECEIVED = Counter(
    "telemetry_received_total",
    "Antal modtagne sensorværdier (SensorTelemetryReceived).",
    ["sensor_type"],
)
ANOMALIES_DETECTED = Counter(
    "anomalies_detected_total",
    "Antal fundne anomalier (AnomalyDetected), fordelt på alvor.",
    ["severity"],
)
