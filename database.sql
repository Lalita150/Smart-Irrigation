-- =====================================================================
-- Smart Irrigation Advisor - Database Schema & Analytical Queries
-- Subject: Data Collection and Database Systems Lab (DCDSL)
-- Engine: SQLite 3
-- Notes: All sensor data is SIMULATED for academic evaluation.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. TABLE DEFINITIONS
-- ---------------------------------------------------------------------

-- Drop existing tables to ensure clean re-initialization if needed
DROP TABLE IF EXISTS irrigation_history;
DROP TABLE IF EXISTS sensor_readings;
DROP TABLE IF EXISTS farms;

-- Table: farms
-- Stores metadata about registered agricultural plots
CREATE TABLE farms (
    farm_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    location TEXT NOT NULL,
    crop_type TEXT NOT NULL,
    area_acres REAL NOT NULL CHECK(area_acres > 0),
    soil_type TEXT NOT NULL CHECK(soil_type IN ('Loamy', 'Clay', 'Sandy', 'Silt', 'Peaty')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: sensor_readings
-- Stores periodic telemetry readings (soil moisture, temperature, humidity, rainfall)
-- Explicitly flagged with is_simulated to avoid claiming live IoT connectivity.
CREATE TABLE sensor_readings (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL,
    soil_moisture_pct REAL NOT NULL CHECK(soil_moisture_pct >= 0.0 AND soil_moisture_pct <= 100.0),
    soil_temperature_c REAL NOT NULL,
    ambient_humidity_pct REAL NOT NULL CHECK(ambient_humidity_pct >= 0.0 AND ambient_humidity_pct <= 100.0),
    rainfall_last_24h_mm REAL NOT NULL DEFAULT 0.0 CHECK(rainfall_last_24h_mm >= 0.0),
    rainfall_forecast_24h_mm REAL NOT NULL DEFAULT 0.0 CHECK(rainfall_forecast_24h_mm >= 0.0),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_simulated INTEGER NOT NULL DEFAULT 1 CHECK(is_simulated IN (0, 1)),
    FOREIGN KEY (farm_id) REFERENCES farms (farm_id) ON DELETE CASCADE
);

-- Table: irrigation_history
-- Records user-executed water dispensation events and system recommendations
CREATE TABLE irrigation_history (
    irrigation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER NOT NULL,
    water_volume_liters REAL NOT NULL CHECK(water_volume_liters > 0.0),
    irrigation_method TEXT NOT NULL CHECK(irrigation_method IN ('Drip', 'Sprinkler', 'Surface/Flood', 'Subsurface')),
    duration_minutes INTEGER CHECK(duration_minutes IS NULL OR duration_minutes > 0),
    recommended_by_system INTEGER NOT NULL DEFAULT 1 CHECK(recommended_by_system IN (0, 1)),
    notes TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (farm_id) REFERENCES farms (farm_id) ON DELETE CASCADE
);

-- Table Indexes for High-Performance Telemetry Lookups & Range Scans
CREATE INDEX IF NOT EXISTS idx_sensor_readings_farm_ts ON sensor_readings(farm_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_ts ON sensor_readings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_history_farm_ts ON irrigation_history(farm_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_history_ts ON irrigation_history(timestamp DESC);

-- ---------------------------------------------------------------------
-- 2. SAMPLE DATA INSERTION (Simulated Academic Test Dataset)
-- ---------------------------------------------------------------------

-- Insert sample farms across various crops and soil types
INSERT INTO farms (farm_id, name, owner_name, location, crop_type, area_acres, soil_type, created_at) VALUES
(1, 'Green Valley Agro', 'Ramesh Patel', 'Zone A - North Ridge', 'Tomato', 3.5, 'Loamy', '2026-09-01 08:00:00'),
(2, 'Sunrise Paddy Fields', 'Sunita Rao', 'Zone B - River Basin', 'Rice', 5.0, 'Clay', '2026-09-01 08:30:00'),
(3, 'Golden Harvest Farm', 'Vikas Sharma', 'Zone C - West Plateau', 'Wheat', 4.0, 'Loamy', '2026-09-02 09:15:00'),
(4, 'Black Soil Cotton Estate', 'Ananya Deshmukh', 'Zone D - South Valley', 'Cotton', 6.0, 'Clay', '2026-09-02 10:00:00'),
(5, 'Blue Sky Orchard & Maize', 'David Fernandez', 'Zone E - East Terraces', 'Maize', 2.5, 'Sandy', '2026-09-03 11:30:00');

-- Insert simulated historical sensor readings (representing dry, wet, and optimal conditions)
INSERT INTO sensor_readings (farm_id, soil_moisture_pct, soil_temperature_c, ambient_humidity_pct, rainfall_last_24h_mm, rainfall_forecast_24h_mm, timestamp, is_simulated) VALUES
-- Farm 1 (Tomato - needs water, low forecast)
(1, 28.5, 31.0, 52.0, 0.0, 1.5, '2026-10-22 06:00:00', 1),
(1, 25.0, 33.5, 48.0, 0.0, 2.0, '2026-10-23 06:00:00', 1),
(1, 22.4, 34.0, 45.0, 0.0, 0.5, '2026-10-24 06:00:00', 1),

-- Farm 2 (Rice - high moisture requirement, rain forecast incoming)
(2, 62.0, 27.5, 80.0, 5.0, 18.0, '2026-10-22 06:30:00', 1),
(2, 58.0, 28.0, 78.0, 2.0, 22.5, '2026-10-23 06:30:00', 1),
(2, 54.0, 28.2, 75.0, 0.0, 25.0, '2026-10-24 06:30:00', 1),

-- Farm 3 (Wheat - moderate moisture, normal)
(3, 34.0, 26.0, 60.0, 0.0, 0.0, '2026-10-22 07:00:00', 1),
(3, 31.5, 27.0, 58.0, 0.0, 0.0, '2026-10-23 07:00:00', 1),
(3, 29.8, 27.5, 55.0, 0.0, 4.0, '2026-10-24 07:00:00', 1),

-- Farm 4 (Cotton - drought-tolerant, low moisture acceptable)
(4, 27.0, 35.0, 40.0, 0.0, 0.0, '2026-10-22 07:30:00', 1),
(4, 26.0, 36.2, 38.0, 0.0, 0.0, '2026-10-23 07:30:00', 1),
(4, 24.5, 36.5, 37.0, 0.0, 0.0, '2026-10-24 07:30:00', 1),

-- Farm 5 (Maize - sandy soil, fast drainage, critical dry)
(5, 23.0, 30.0, 50.0, 0.0, 1.0, '2026-10-22 08:00:00', 1),
(5, 19.5, 32.0, 47.0, 0.0, 0.0, '2026-10-23 08:00:00', 1),
(5, 17.2, 33.0, 44.0, 0.0, 0.0, '2026-10-24 08:00:00', 1);

-- Insert sample irrigation logs demonstrating varied water usage across methods
INSERT INTO irrigation_history (farm_id, water_volume_liters, irrigation_method, duration_minutes, recommended_by_system, notes, timestamp) VALUES
(1, 12000.0, 'Drip', 120, 1, 'Morning schedule per advisor recommendation', '2026-10-18 07:00:00'),
(1, 11500.0, 'Drip', 115, 1, 'Regular cycle following soil moisture drop', '2026-10-21 07:15:00'),
(2, 45000.0, 'Surface/Flood', 240, 0, 'Manual flooding before expected dry spell', '2026-10-15 06:00:00'),
(2, 38000.0, 'Surface/Flood', 200, 1, 'Flooding cycle maintaining rice water layer', '2026-10-19 06:30:00'),
(3, 15000.0, 'Sprinkler', 90, 1, 'Sprinkler routine during early germination', '2026-10-17 08:00:00'),
(3, 14200.0, 'Sprinkler', 85, 1, 'Sprinkler cycle after moisture deficit alert', '2026-10-20 08:00:00'),
(4, 8500.0, 'Drip', 90, 1, 'Water-saving drip cycle for cotton crop', '2026-10-16 07:00:00'),
(4, 9000.0, 'Drip', 95, 1, 'Drip irrigation applied during hot afternoon', '2026-10-20 17:00:00'),
(5, 7500.0, 'Drip', 60, 1, 'Frequent light irrigation for sandy soil maize', '2026-10-19 06:45:00'),
(5, 8000.0, 'Sprinkler', 70, 1, 'Sprinkler supplement due to high evapotranspiration', '2026-10-22 07:00:00');

-- ---------------------------------------------------------------------
-- 3. ADVANCED SQL QUERIES (Demonstrating DCDSL Project Requirements)
-- ---------------------------------------------------------------------

-- QUERY 1: Multi-Table JOIN with GROUP BY and Aggregate Functions
-- Purpose: Summarizes irrigation count, total water consumption, and average water per event for each farm.
SELECT
    f.farm_id,
    f.name AS farm_name,
    f.crop_type,
    f.area_acres,
    f.soil_type,
    COUNT(i.irrigation_id) AS total_irrigation_events,
    ROUND(COALESCE(SUM(i.water_volume_liters), 0.0), 2) AS total_water_liters,
    ROUND(COALESCE(AVG(i.water_volume_liters), 0.0), 2) AS avg_water_per_event_liters
FROM farms f
LEFT JOIN irrigation_history i ON f.farm_id = i.farm_id
GROUP BY f.farm_id, f.name, f.crop_type, f.area_acres, f.soil_type
ORDER BY total_water_liters DESC;

-- QUERY 2: JOIN with GROUP BY and HAVING Clause
-- Purpose: Identifies high water-consuming farms that have logged at least 2 irrigation events AND used over 20,000 Liters total.
SELECT
    f.farm_id,
    f.name AS farm_name,
    f.crop_type,
    COUNT(i.irrigation_id) AS irrigation_count,
    ROUND(SUM(i.water_volume_liters), 2) AS total_water_consumed_liters,
    ROUND(AVG(i.water_volume_liters), 2) AS avg_consumption_liters
FROM farms f
JOIN irrigation_history i ON f.farm_id = i.farm_id
GROUP BY f.farm_id, f.name, f.crop_type
HAVING COUNT(i.irrigation_id) >= 2 AND SUM(i.water_volume_liters) > 20000.0
ORDER BY total_water_consumed_liters DESC;

-- QUERY 3: Subquery in HAVING Clause (Comparative Aggregate Filter)
-- Purpose: Identifies farms whose average recorded soil moisture is strictly lower than the overall network average across all farms.
SELECT
    f.farm_id,
    f.name AS farm_name,
    f.crop_type,
    f.soil_type,
    ROUND(AVG(s.soil_moisture_pct), 2) AS farm_avg_moisture_pct,
    ROUND((SELECT AVG(soil_moisture_pct) FROM sensor_readings), 2) AS network_avg_moisture_pct
FROM farms f
JOIN sensor_readings s ON f.farm_id = s.farm_id
GROUP BY f.farm_id, f.name, f.crop_type, f.soil_type
HAVING AVG(s.soil_moisture_pct) < (
    SELECT AVG(soil_moisture_pct) FROM sensor_readings
)
ORDER BY farm_avg_moisture_pct ASC;

-- QUERY 4: Correlated Subqueries in SELECT (Latest Telemetry Snapshot)
-- Purpose: Extracts the most recent simulated reading for each farm without requiring complex window functions.
SELECT
    f.farm_id,
    f.name AS farm_name,
    f.crop_type,
    f.area_acres,
    (SELECT s.soil_moisture_pct
     FROM sensor_readings s
     WHERE s.farm_id = f.farm_id
     ORDER BY s.timestamp DESC, s.reading_id DESC
     LIMIT 1) AS latest_soil_moisture_pct,
    (SELECT s.soil_temperature_c
     FROM sensor_readings s
     WHERE s.farm_id = f.farm_id
     ORDER BY s.timestamp DESC, s.reading_id DESC
     LIMIT 1) AS latest_soil_temp_c,
    (SELECT s.rainfall_forecast_24h_mm
     FROM sensor_readings s
     WHERE s.farm_id = f.farm_id
     ORDER BY s.timestamp DESC, s.reading_id DESC
     LIMIT 1) AS forecast_rain_mm,
    (SELECT s.timestamp
     FROM sensor_readings s
     WHERE s.farm_id = f.farm_id
     ORDER BY s.timestamp DESC, s.reading_id DESC
     LIMIT 1) AS last_reading_time
FROM farms f
ORDER BY f.farm_id ASC;

-- QUERY 5: Nested Derived Table Subquery with Fleet Benchmark Variance
-- Purpose: Computes water intensity (Liters per acre) for each farm and calculates its variance against the average intensity across all farms.
SELECT
    farm_metrics.farm_id,
    farm_metrics.farm_name,
    farm_metrics.crop_type,
    farm_metrics.area_acres,
    farm_metrics.total_water_liters,
    farm_metrics.liters_per_acre,
    ROUND(farm_metrics.liters_per_acre - (
        SELECT AVG(sub.total_water / sub.area)
        FROM (
            SELECT f2.area_acres AS area, SUM(i2.water_volume_liters) AS total_water
            FROM farms f2
            JOIN irrigation_history i2 ON f2.farm_id = i2.farm_id
            GROUP BY f2.farm_id, f2.area_acres
        ) AS sub
    ), 2) AS variance_from_fleet_intensity
FROM (
    SELECT
        f.farm_id,
        f.name AS farm_name,
        f.crop_type,
        f.area_acres,
        ROUND(SUM(i.water_volume_liters), 2) AS total_water_liters,
        ROUND(SUM(i.water_volume_liters) / f.area_acres, 2) AS liters_per_acre
    FROM farms f
    JOIN irrigation_history i ON f.farm_id = i.farm_id
    GROUP BY f.farm_id, f.name, f.crop_type, f.area_acres
) AS farm_metrics
ORDER BY farm_metrics.liters_per_acre DESC;
