-- Kører automatisk første gang MySQL-containeren starter.
-- Tabellerne følger ordforrådet fra Event Storming (Delopgave 1).

CREATE TABLE IF NOT EXISTS assets (
    asset_id                   VARCHAR(64)  NOT NULL PRIMARY KEY,
    vibration_threshold        DECIMAL(6,2) NOT NULL DEFAULT 7.50,  -- mm/s
    is_flagged_for_maintenance BOOLEAN      NOT NULL DEFAULT FALSE
);

-- Domænehændelser: SensorTelemetryReceived og AnomalyDetected
CREATE TABLE IF NOT EXISTS domain_events (
    event_id    CHAR(36)    NOT NULL PRIMARY KEY,
    event_type  VARCHAR(64) NOT NULL,
    asset_id    VARCHAR(64) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    payload     JSON        NOT NULL,
    INDEX idx_events_asset (asset_id, occurred_at),
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);

-- Alarmer, som kontrolcentret skal reagere på
CREATE TABLE IF NOT EXISTS alarms (
    alarm_id           CHAR(36)    NOT NULL PRIMARY KEY,
    asset_id           VARCHAR(64) NOT NULL,
    severity           VARCHAR(16) NOT NULL,
    message            VARCHAR(255) NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    created_at         DATETIME(6) NOT NULL,
    caused_by_event_id CHAR(36)    NOT NULL,
    INDEX idx_alarms_asset (asset_id, created_at),
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id),
    FOREIGN KEY (caused_by_event_id) REFERENCES domain_events(event_id)
);

-- Testdata: én vindmølle med grænseværdi 7,5 mm/s
INSERT INTO assets (asset_id, vibration_threshold) VALUES ('WTG-001', 7.50);
