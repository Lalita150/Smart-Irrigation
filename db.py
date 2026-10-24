"""
db.py - SQLite Database Access Layer
====================================
Handles connection management, table initialization, and parameterized CRUD
operations for the Smart Irrigation Advisor system.

Guarantees:
- Strict use of parameterized SQL queries (protects against SQL Injection).
- Proper transaction commit/rollback via context managers.
- Clear exception propagation and descriptive error handling.
- Foreign key constraints enabled on all connections.
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional, Union
import pandas as pd

DEFAULT_DB_NAME = "smart_irrigation.db"
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DB_NAME)
DEFAULT_SQL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.sql")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Returns an SQLite connection with Row factory and Foreign Keys enabled.
    """
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_database(db_path: Optional[str] = None, sql_script_path: Optional[str] = None) -> None:
    """
    Initializes the SQLite database using the DDL and seed data in database.sql.
    Re-creates all tables (drops existing tables). Use init_database_safe to preserve existing records.
    """
    target_db = db_path or DEFAULT_DB_PATH
    script_file = sql_script_path or DEFAULT_SQL_PATH

    if not os.path.exists(script_file):
        raise FileNotFoundError(f"Database schema file not found at: {script_file}")

    with open(script_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # SQLite executescript handles multiple statements and executes DDL/DML safely
    conn = get_connection(target_db)
    try:
        with conn:
            conn.executescript(sql_content)
    finally:
        conn.close()


def init_database_safe(db_path: Optional[str] = None) -> bool:
    """
    Safely ensures tables exist WITHOUT dropping any existing data.
    If the tables already contain data, all existing records are preserved.
    Only seeds sample records if the farms table is completely empty.

    Returns:
        True if seed records were inserted, False if existing data was preserved.
    """
    target_db = db_path or DEFAULT_DB_PATH
    conn = get_connection(target_db)
    try:
        with conn:
            # Create tables only if they do not exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS farms (
                    farm_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    crop_type TEXT NOT NULL,
                    area_acres REAL NOT NULL CHECK(area_acres > 0),
                    soil_type TEXT NOT NULL CHECK(soil_type IN ('Loamy', 'Clay', 'Sandy', 'Silt', 'Peaty')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
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
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS irrigation_history (
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
            """)

            # Check if farms table is empty
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM farms;")
            count = cursor.fetchone()[0]

            # Ensure high-performance query indexes exist
            create_database_indexes(conn=conn, db_path=target_db)

            if count == 0:
                # Only seed default sample data if table is completely empty
                # Call init_database to populate initial seed dataset
                init_database(db_path=target_db)
                return True
            return False
    finally:
        conn.close()


def create_database_indexes(
    db_path: Optional[Union[str, sqlite3.Connection]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """
    Creates composite and single-column indexes on high-frequency query columns
    (farm_id and timestamp) without deleting or modifying existing records.
    Safe to execute repeatedly (idempotent) using CREATE INDEX IF NOT EXISTS.

    Accepts:
    - db_path: SQLite database file path (str), or an active sqlite3.Connection, or None (defaults to DEFAULT_DB_PATH).
    - conn: Optional active sqlite3.Connection.
    """
    target_conn: Optional[sqlite3.Connection] = None
    should_close = False

    if conn is not None and isinstance(conn, sqlite3.Connection):
        target_conn = conn
        should_close = False
    elif isinstance(db_path, sqlite3.Connection):
        target_conn = db_path
        should_close = False
    else:
        target_db = (db_path if isinstance(db_path, str) else None) or DEFAULT_DB_PATH
        target_conn = get_connection(target_db)
        should_close = True

    try:
        with target_conn:
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_farm_ts ON sensor_readings(farm_id, timestamp DESC);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_ts ON sensor_readings(timestamp DESC);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_irrigation_history_farm_ts ON irrigation_history(farm_id, timestamp DESC);")
            target_conn.execute("CREATE INDEX IF NOT EXISTS idx_irrigation_history_ts ON irrigation_history(timestamp DESC);")
    finally:
        if should_close and target_conn is not None:
            target_conn.close()


def ensure_database_exists(db_path: Optional[str] = None) -> None:
    """
    Checks if database exists; if not, automatically initializes it safely.
    Ensures query indexes are verified.
    """
    target_db = db_path or DEFAULT_DB_PATH
    if not os.path.exists(target_db):
        init_database(db_path=target_db)
    else:
        init_database_safe(db_path=target_db)
    create_database_indexes(db_path=target_db)



# ---------------------------------------------------------------------
# Farm Operations
# ---------------------------------------------------------------------

def get_all_farms(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves all registered farms.
    """
    ensure_database_exists(db_path)
    query = """
        SELECT farm_id, name, owner_name, location, crop_type, area_acres, soil_type, created_at
        FROM farms
        ORDER BY farm_id ASC;
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_farm_by_id(farm_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single farm by its primary key using a parameterized query.
    """
    ensure_database_exists(db_path)
    if not isinstance(farm_id, int) or farm_id <= 0:
        raise ValueError(f"Invalid farm_id: {farm_id}. Must be a positive integer.")

    query = """
        SELECT farm_id, name, owner_name, location, crop_type, area_acres, soil_type, created_at
        FROM farms
        WHERE farm_id = ?;
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query, (farm_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_farm(
    name: str,
    owner_name: str,
    location: str,
    crop_type: str,
    area_acres: float,
    soil_type: str,
    db_path: Optional[str] = None,
) -> int:
    """
    Adds a new agricultural plot to the database using a parameterized query.
    """
    ensure_database_exists(db_path)
    if not name or not owner_name:
        raise ValueError("Farm name and owner name are required.")
    if area_acres <= 0:
        raise ValueError(f"Area ({area_acres} acres) must be positive.")
    valid_soils = {"Loamy", "Clay", "Sandy", "Silt", "Peaty"}
    if soil_type not in valid_soils:
        raise ValueError(f"Soil type must be one of {sorted(list(valid_soils))}")

    query = """
        INSERT INTO farms (name, owner_name, location, crop_type, area_acres, soil_type)
        VALUES (?, ?, ?, ?, ?, ?);
    """
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(query, (name, owner_name, location, crop_type, float(area_acres), soil_type))
            return cursor.lastrowid
    finally:
        conn.close()



# ---------------------------------------------------------------------
# Sensor Readings Operations
# ---------------------------------------------------------------------

def get_latest_sensor_reading(farm_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent simulated telemetry reading for a given farm.
    """
    ensure_database_exists(db_path)
    query = """
        SELECT reading_id, farm_id, soil_moisture_pct, soil_temperature_c,
               ambient_humidity_pct, rainfall_last_24h_mm, rainfall_forecast_24h_mm,
               timestamp, is_simulated
        FROM sensor_readings
        WHERE farm_id = ?
        ORDER BY timestamp DESC, reading_id DESC
        LIMIT 1;
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query, (farm_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_sensor_reading(
    farm_id: int,
    soil_moisture_pct: float,
    soil_temperature_c: float,
    ambient_humidity_pct: float,
    rainfall_last_24h_mm: float = 0.0,
    rainfall_forecast_24h_mm: float = 0.0,
    is_simulated: int = 1,
    db_path: Optional[str] = None,
) -> int:
    """
    Records a new sensor reading using parameterized inputs and domain validation.
    """
    ensure_database_exists(db_path)

    # Input validations
    if not (0.0 <= soil_moisture_pct <= 100.0):
        raise ValueError(f"Soil moisture {soil_moisture_pct}% out of valid range (0-100%).")
    if not (0.0 <= ambient_humidity_pct <= 100.0):
        raise ValueError(f"Humidity {ambient_humidity_pct}% out of valid range (0-100%).")
    if rainfall_last_24h_mm < 0.0 or rainfall_forecast_24h_mm < 0.0:
        raise ValueError("Rainfall values must be non-negative.")

    query = """
        INSERT INTO sensor_readings (
            farm_id, soil_moisture_pct, soil_temperature_c, ambient_humidity_pct,
            rainfall_last_24h_mm, rainfall_forecast_24h_mm, is_simulated
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    farm_id,
                    float(soil_moisture_pct),
                    float(soil_temperature_c),
                    float(ambient_humidity_pct),
                    float(rainfall_last_24h_mm),
                    float(rainfall_forecast_24h_mm),
                    int(is_simulated),
                ),
            )
            return cursor.lastrowid
    finally:
        conn.close()


def get_sensor_readings_history(farm_id: Optional[int] = None, limit: int = 50, db_path: Optional[str] = None) -> pd.DataFrame:
    """
    Retrieves sensor telemetry history as a Pandas DataFrame.
    """
    ensure_database_exists(db_path)
    conn = get_connection(db_path)
    try:
        if farm_id is not None:
            query = """
                SELECT s.reading_id, s.farm_id, f.name AS farm_name, f.crop_type,
                       s.soil_moisture_pct, s.soil_temperature_c, s.ambient_humidity_pct,
                       s.rainfall_last_24h_mm, s.rainfall_forecast_24h_mm,
                       s.timestamp, s.is_simulated
                FROM sensor_readings s
                JOIN farms f ON s.farm_id = f.farm_id
                WHERE s.farm_id = ?
                ORDER BY s.timestamp DESC
                LIMIT ?;
            """
            df = pd.read_sql_query(query, conn, params=(farm_id, limit))
        else:
            query = """
                SELECT s.reading_id, s.farm_id, f.name AS farm_name, f.crop_type,
                       s.soil_moisture_pct, s.soil_temperature_c, s.ambient_humidity_pct,
                       s.rainfall_last_24h_mm, s.rainfall_forecast_24h_mm,
                       s.timestamp, s.is_simulated
                FROM sensor_readings s
                JOIN farms f ON s.farm_id = f.farm_id
                ORDER BY s.timestamp DESC
                LIMIT ?;
            """
            df = pd.read_sql_query(query, conn, params=(limit,))
        return df
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Irrigation History Operations
# ---------------------------------------------------------------------

def record_irrigation_event(
    farm_id: int,
    water_volume_liters: float,
    irrigation_method: str,
    duration_minutes: Optional[int] = None,
    recommended_by_system: int = 1,
    notes: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Inserts a newly completed irrigation log into irrigation_history.
    Uses parameterized query and enforces database-level integrity.
    """
    ensure_database_exists(db_path)

    if water_volume_liters <= 0.0:
        raise ValueError(f"Water volume ({water_volume_liters} L) must be greater than 0.")

    valid_methods = {"Drip", "Sprinkler", "Surface/Flood", "Subsurface"}
    if irrigation_method not in valid_methods:
        raise ValueError(
            f"Invalid irrigation method '{irrigation_method}'. Allowed: {', '.join(sorted(valid_methods))}"
        )

    if duration_minutes is not None and duration_minutes <= 0:
        raise ValueError(f"Duration ({duration_minutes} min) must be a positive integer if provided.")

    query = """
        INSERT INTO irrigation_history (
            farm_id, water_volume_liters, irrigation_method, duration_minutes,
            recommended_by_system, notes
        ) VALUES (?, ?, ?, ?, ?, ?);
    """
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    farm_id,
                    float(water_volume_liters),
                    irrigation_method,
                    duration_minutes,
                    int(recommended_by_system),
                    notes or "",
                ),
            )
            return cursor.lastrowid
    finally:
        conn.close()


def get_irrigation_history(farm_id: Optional[int] = None, limit: int = 100, db_path: Optional[str] = None) -> pd.DataFrame:
    """
    Retrieves irrigation history joined with farm details.
    """
    ensure_database_exists(db_path)
    conn = get_connection(db_path)
    try:
        if farm_id is not None:
            query = """
                SELECT i.irrigation_id, i.farm_id, f.name AS farm_name, f.crop_type,
                       f.area_acres, i.water_volume_liters, i.irrigation_method,
                       i.duration_minutes, i.recommended_by_system, i.notes, i.timestamp
                FROM irrigation_history i
                JOIN farms f ON i.farm_id = f.farm_id
                WHERE i.farm_id = ?
                ORDER BY i.timestamp DESC
                LIMIT ?;
            """
            df = pd.read_sql_query(query, conn, params=(farm_id, limit))
        else:
            query = """
                SELECT i.irrigation_id, i.farm_id, f.name AS farm_name, f.crop_type,
                       f.area_acres, i.water_volume_liters, i.irrigation_method,
                       i.duration_minutes, i.recommended_by_system, i.notes, i.timestamp
                FROM irrigation_history i
                JOIN farms f ON i.farm_id = f.farm_id
                ORDER BY i.timestamp DESC
                LIMIT ?;
            """
            df = pd.read_sql_query(query, conn, params=(limit,))
        return df
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Advanced Analytical Queries (DCDSL Evaluation Showcase)
# ---------------------------------------------------------------------

ANALYTICAL_QUERIES = {
    "query1_join_groupby": {
        "title": "Query 1: Farm Consumption Aggregation (JOIN & GROUP BY)",
        "description": "Computes total water consumed and average volume per event across all registered farms.",
        "sql": """
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
        """,
    },
    "query2_having_filter": {
        "title": "Query 2: High-Consumption Outlier Filter (JOIN, GROUP BY, HAVING)",
        "description": "Filters for farms with at least 2 irrigation events that consumed over 15,000 Liters of water.",
        "sql": """
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
            HAVING COUNT(i.irrigation_id) >= 2 AND SUM(i.water_volume_liters) > 15000.0
            ORDER BY total_water_consumed_liters DESC;
        """,
    },
    "query3_subquery_having": {
        "title": "Query 3: Below-Network Average Moisture (Subquery in HAVING)",
        "description": "Employs an aggregate subquery to isolate farms whose average soil moisture is lower than the entire network's average.",
        "sql": """
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
        """,
    },
    "query4_correlated_subquery": {
        "title": "Query 4: Farm Telemetry Snapshot (Correlated Subquery in SELECT)",
        "description": "Extracts the latest simulated soil moisture and forecast rain for each farm without requiring window functions.",
        "sql": """
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
        """,
    },
    "query5_nested_subquery": {
        "title": "Query 5: Per-Acre Intensity & Fleet Variance (Nested Derived Table)",
        "description": "Calculates water intensity (Liters/Acre) per farm and compares against the network baseline via nested derived tables.",
        "sql": """
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
        """,
    },
}


def execute_analytical_query(query_key: str, db_path: Optional[str] = None) -> pd.DataFrame:
    """
    Executes one of the 5 pre-defined DCDSL analytical queries and returns a Pandas DataFrame.
    """
    ensure_database_exists(db_path)
    if query_key not in ANALYTICAL_QUERIES:
        raise KeyError(f"Unknown query key: {query_key}. Available: {list(ANALYTICAL_QUERIES.keys())}")

    sql = ANALYTICAL_QUERIES[query_key]["sql"]
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def execute_safe_readonly_sql(sql: str, db_path: Optional[str] = None) -> pd.DataFrame:
    """
    Safely executes user-supplied SQL in strict READ-ONLY mode.
    Enforces security:
    - Blocks DROP, ALTER, DELETE, UPDATE, INSERT, ATTACH, DETACH, PRAGMA write commands.
    - Enables SQLite PRAGMA query_only = ON on the connection.
    - Limits result rows to prevent Denial-of-Service memory exhaustion.
    """
    ensure_database_exists(db_path)
    clean_sql = sql.strip()
    upper_sql = clean_sql.upper()

    if not upper_sql.startswith("SELECT") and not upper_sql.startswith("WITH"):
        raise PermissionError("Security Policy Violation: Only read-only SELECT or WITH statements are permitted.")

    forbidden_patterns = [
        r"\bDROP\b", r"\bALTER\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
        r"\bTRUNCATE\b", r"\bREPLACE\b", r"\bCREATE\b", r"\bATTACH\b", r"\bDETACH\b",
        r"\bPRAGMA\b", r"\bVACUUM\b", r"\bREINDEX\b", r"\bEXEC\b"
    ]
    for pattern in forbidden_patterns:
        if re.search(pattern, upper_sql):
            clean_word = pattern.replace(r"\b", "")
            raise PermissionError(f"Security Policy Violation: Keyword '{clean_word}' is forbidden in the read-only laboratory console.")

    conn = get_connection(db_path)
    try:
        conn.execute("PRAGMA query_only = ON;")
        cursor = conn.cursor()
        cursor.execute(clean_sql)
        cols = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(500)
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def run_join_query_demo(
    join_type: str = "LEFT",
    farm_id: Optional[int] = None,
    crop_type: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[str, pd.DataFrame]:
    """
    Demonstrates SQL JOIN queries (INNER JOIN or LEFT JOIN) linking farms and telemetry/irrigation.
    Returns (sql_query_string, result_dataframe).
    """
    ensure_database_exists(db_path)
    filters = []
    params: List[Any] = []

    if farm_id is not None:
        filters.append("f.farm_id = ?")
        params.append(int(farm_id))
    if crop_type and crop_type != "All Crops":
        filters.append("f.crop_type = ?")
        params.append(crop_type)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    if join_type == "INNER":
        sql = f"""
            SELECT
                f.farm_id,
                f.name AS farm_name,
                f.crop_type,
                f.area_acres,
                s.reading_id,
                s.soil_moisture_pct,
                s.soil_temperature_c,
                s.ambient_humidity_pct,
                s.rainfall_last_24h_mm,
                s.timestamp AS reading_time
            FROM farms f
            INNER JOIN sensor_readings s ON f.farm_id = s.farm_id
            {where_clause}
            ORDER BY s.timestamp DESC
            LIMIT 50;
        """
    else:
        sql = f"""
            SELECT
                f.farm_id,
                f.name AS farm_name,
                f.crop_type,
                f.soil_type,
                f.area_acres,
                COUNT(i.irrigation_id) AS total_events,
                ROUND(COALESCE(SUM(i.water_volume_liters), 0.0), 2) AS total_water_liters,
                ROUND(COALESCE(AVG(i.water_volume_liters), 0.0), 2) AS avg_event_liters,
                COALESCE(MAX(i.timestamp), 'No events recorded') AS last_irrigation_date
            FROM farms f
            LEFT JOIN irrigation_history i ON f.farm_id = i.farm_id
            {where_clause}
            GROUP BY f.farm_id, f.name, f.crop_type, f.soil_type, f.area_acres
            ORDER BY total_water_liters DESC;
        """

    conn = get_connection(db_path)
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return sql.strip(), df
    finally:
        conn.close()


def run_groupby_having_demo(
    min_water_liters: float = 15000.0,
    crop_type: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[str, pd.DataFrame]:
    """
    Demonstrates GROUP BY and HAVING clauses filtering high-volume outlier plots.
    Returns (sql_query_string, result_dataframe).
    """
    ensure_database_exists(db_path)
    where_parts = []
    params: List[Any] = []

    if crop_type and crop_type != "All Crops":
        where_parts.append("f.crop_type = ?")
        params.append(crop_type)

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    params.extend([float(min_water_liters)])

    sql = f"""
        SELECT
            f.farm_id,
            f.name AS farm_name,
            f.crop_type,
            f.soil_type,
            COUNT(i.irrigation_id) AS irrigation_count,
            ROUND(SUM(i.water_volume_liters), 2) AS total_water_liters,
            ROUND(AVG(i.water_volume_liters), 2) AS avg_consumption_liters
        FROM farms f
        JOIN irrigation_history i ON f.farm_id = i.farm_id
        {where_clause}
        GROUP BY f.farm_id, f.name, f.crop_type, f.soil_type
        HAVING SUM(i.water_volume_liters) >= ?
        ORDER BY total_water_liters DESC;
    """

    conn = get_connection(db_path)
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return sql.strip(), df
    finally:
        conn.close()


def run_subquery_demo(
    subquery_type: str = "correlated",
    farm_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Tuple[str, pd.DataFrame]:
    """
    Demonstrates advanced SQL subqueries: Correlated in SELECT, Subquery in HAVING, or Nested Derived Table.
    Returns (sql_query_string, result_dataframe).
    """
    ensure_database_exists(db_path)
    conn = get_connection(db_path)
    try:
        if subquery_type == "having_subquery":
            # Farms below global average moisture
            sql = """
                SELECT
                    f.farm_id,
                    f.name AS farm_name,
                    f.crop_type,
                    f.soil_type,
                    ROUND(AVG(s.soil_moisture_pct), 2) AS farm_avg_moisture_pct,
                    ROUND((SELECT AVG(soil_moisture_pct) FROM sensor_readings), 2) AS fleet_avg_moisture_pct
                FROM farms f
                JOIN sensor_readings s ON f.farm_id = s.farm_id
                GROUP BY f.farm_id, f.name, f.crop_type, f.soil_type
                HAVING AVG(s.soil_moisture_pct) < (
                    SELECT AVG(soil_moisture_pct) FROM sensor_readings
                )
                ORDER BY farm_avg_moisture_pct ASC;
            """
            return sql.strip(), pd.read_sql_query(sql, conn)
        elif subquery_type == "nested_derived_table":
            # Per-acre intensity & fleet variance
            sql = ANALYTICAL_QUERIES["query5_nested_subquery"]["sql"]
            return sql.strip(), pd.read_sql_query(sql, conn)
        else:
            # Correlated subquery in SELECT
            farm_filter = f"WHERE f.farm_id = {int(farm_id)}" if farm_id else ""
            sql = f"""
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
                {farm_filter}
                ORDER BY f.farm_id ASC;
            """
            return sql.strip(), pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def run_aggregates_demo(
    farm_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Tuple[str, pd.DataFrame]:
    """
    Demonstrates SQL aggregate functions (COUNT, SUM, AVG, MIN, MAX, ROUND)
    across irrigation dispensation and telemetry readings.
    """
    ensure_database_exists(db_path)
    conn = get_connection(db_path)
    try:
        where_clause = f"WHERE farm_id = {int(farm_id)}" if farm_id else ""
        sql = f"""
            SELECT
                COUNT(reading_id) AS total_readings_count,
                ROUND(AVG(soil_moisture_pct), 2) AS avg_soil_moisture_pct,
                ROUND(MIN(soil_moisture_pct), 2) AS min_soil_moisture_pct,
                ROUND(MAX(soil_moisture_pct), 2) AS max_soil_moisture_pct,
                ROUND(AVG(soil_temperature_c), 2) AS avg_temperature_c,
                ROUND(AVG(ambient_humidity_pct), 2) AS avg_humidity_pct,
                ROUND(MAX(rainfall_last_24h_mm), 2) AS max_rainfall_mm,
                ROUND(SUM(rainfall_last_24h_mm), 2) AS total_recorded_rainfall_mm
            FROM sensor_readings
            {where_clause};
        """
        return sql.strip(), pd.read_sql_query(sql, conn)
    finally:
        conn.close()

