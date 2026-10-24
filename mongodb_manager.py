"""
mongodb_manager.py - MongoDB NoSQL Manager for Smart Irrigation Advisor
========================================================================
Subject: Data Collection and Database Systems Lab (DCDSL)
Role: NoSQL telemetry persistence layer for time-series sensor readings.

Key Architectural Responsibilities:
1. Connects to MongoDB via the MONGODB_URI environment variable.
2. Credentials are never hardcoded; loaded strictly from environment or .env.
3. Manages the 'sensor_readings' collection for high-frequency sensor telemetry.
4. Provides robust CRUD operations with domain validation and error handling.
5. Implements connection-status checking with graceful fallback:
   If MongoDB is offline or unconfigured, functions fail safely and notify the
   caller, allowing the application to continue using SQLite for telemetry.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

# Optional PyMongo import with graceful degradation
try:
    import pymongo
    from pymongo import MongoClient
    from pymongo.collection import Collection
    from pymongo.database import Database
    from pymongo.errors import (
        ConfigurationError,
        ConnectionFailure,
        OperationFailure,
        PyMongoError,
        ServerSelectionTimeoutError,
    )
    from bson import ObjectId
    HAS_PYMONGO = True
except ImportError:
    pymongo = None
    MongoClient = None
    Collection = None
    Database = None
    ObjectId = None
    HAS_PYMONGO = False


def _load_env_file() -> None:
    """
    Lightweight loader for .env configuration.
    Uses python-dotenv if installed, or falls back to standard text parsing.
    Prevents hardcoded credentials while maintaining zero-dependency simplicity.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except ImportError:
        pass

    # Fallback parser for root-level .env file
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass


# Automatically attempt to load environment on module import
_load_env_file()

# Environment variable name
ENV_MONGODB_URI = "MONGODB_URI"
DEFAULT_DB_NAME = "smart_irrigation_db"
COLLECTION_SENSOR_READINGS = "sensor_readings"

# Cached singleton client and connection state
_cached_client: Optional[Any] = None
_cached_uri: Optional[str] = None


def get_mongodb_uri() -> Optional[str]:
    """
    Retrieves the MongoDB connection URI from environment variables or Streamlit secrets.
    Returns None if MONGODB_URI is unset or blank.
    """
    _load_env_file()
    uri = os.getenv(ENV_MONGODB_URI, "").strip()
    if not uri:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and ENV_MONGODB_URI in st.secrets:
                uri = str(st.secrets[ENV_MONGODB_URI]).strip()
        except Exception:
            pass
    return uri if uri else None



def get_mongo_client(
    uri: Optional[str] = None,
    timeout_ms: int = 2500,
) -> Optional[Any]:
    """
    Returns a PyMongo MongoClient instance. Reuses existing client if URI matches.
    Configured with a brief serverSelectionTimeoutMS so UI components never freeze
    when MongoDB is unreachable.
    """
    global _cached_client, _cached_uri

    if not HAS_PYMONGO:
        return None

    target_uri = uri or get_mongodb_uri()
    if not target_uri:
        return None

    if _cached_client is not None and _cached_uri == target_uri:
        return _cached_client

    try:
        client = MongoClient(
            target_uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
            appname="AgriPulse-SmartIrrigation",
        )
        _cached_client = client
        _cached_uri = target_uri
        return client
    except Exception:
        return None


def get_database(
    db_name: Optional[str] = None,
    client: Optional[Any] = None,
) -> Optional[Any]:
    """
    Retrieves the target MongoDB database.
    If the URI contains a database name, PyMongo respects it; otherwise falls back to DEFAULT_DB_NAME.
    """
    active_client = client or get_mongo_client()
    if active_client is None:
        return None

    try:
        # Check if database is specified in URI
        default_db = active_client.get_default_database()
        if default_db is not None:
            return default_db
    except (ConfigurationError, Exception):
        pass

    target_db_name = db_name or DEFAULT_DB_NAME
    return active_client[target_db_name]


def get_sensor_collection(client: Optional[Any] = None) -> Optional[Any]:
    """
    Retrieves the 'sensor_readings' collection and verifies index presence.
    """
    db = get_database(client=client)
    if db is None:
        return None

    coll = db[COLLECTION_SENSOR_READINGS]

    # Best-effort background index creation for fast queries by farm & timestamp
    try:
        coll.create_index([("farm_id", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)], background=True)
    except Exception:
        pass

    return coll


# =====================================================================
# Connection Status & Diagnostics
# =====================================================================

def get_connection_status(timeout_ms: int = 800) -> Tuple[str, str, bool]:
    """
    Validates MongoDB connectivity and returns a 3-state status tuple:
    - status_code: 'Connected', 'Offline', or 'Not Configured'
    - message: descriptive diagnostic information
    - is_connected: boolean indicator

    Short default timeout (800ms) prevents UI blocking when MongoDB is unavailable.
    """
    if not HAS_PYMONGO:
        return "Not Configured", "Python library 'pymongo' is not installed in the environment.", False

    uri = get_mongodb_uri()
    if not uri:
        return "Not Configured", f"Environment variable '{ENV_MONGODB_URI}' is not set or empty. See .env.example.", False

    # Mask credentials for safe display in diagnostics
    masked_uri = re.sub(r":([^@]+)@", ":****@", uri)

    try:
        client = get_mongo_client(uri, timeout_ms=timeout_ms)
        if client is None:
            return "Offline", f"Could not initialize MongoClient for URI: {masked_uri}", False

        # Ping the server to verify physical network / auth handshake
        client.admin.command("ping")

        # Fetch server build info for diagnostics
        try:
            build_info = client.admin.command("buildInfo")
            version = build_info.get("version", "unknown")
            return "Connected", f"Connected to MongoDB v{version} ({masked_uri})", True
        except Exception:
            return "Connected", f"Connected to MongoDB ({masked_uri})", True

    except ServerSelectionTimeoutError as e:
        return "Offline", f"Connection timed out ({timeout_ms}ms). Server unreachable at {masked_uri}. ({e})", False
    except ConnectionFailure as e:
        return "Offline", f"Connection failed to {masked_uri}. ({e})", False
    except OperationFailure as e:
        return "Offline", f"Authentication/permission error on {masked_uri}. ({e})", False
    except Exception as e:
        return "Offline", f"MongoDB error: {type(e).__name__}: {e}", False


def check_connection(timeout_ms: int = 1200) -> Tuple[bool, str]:
    """
    Validates MongoDB connectivity with zero guesswork:
    Returns (True, message) if accessible, (False, message) otherwise.
    """
    status, msg, is_connected = get_connection_status(timeout_ms=timeout_ms)
    return is_connected, msg



# =====================================================================
# CRUD OPERATIONS: SENSOR READINGS COLLECTION
# =====================================================================

def insert_sensor_reading(
    farm_id: int,
    soil_moisture_pct: float,
    soil_temperature_c: float,
    humidity_pct: float,
    rainfall_mm: float = 0.0,
    rainfall_forecast_24h_mm: Optional[float] = None,
    is_simulated: int = 1,
    timestamp: Optional[Union[str, datetime.datetime]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Create (Insert): Adds a new telemetry document to MongoDB 'sensor_readings'.

    Schema:
    - farm_id: int (Relational key linking to SQLite farms table)
    - timestamp: ISO datetime string
    - soil_moisture_pct: float (0.0 to 100.0)
    - soil_temperature_c: float
    - humidity_pct: float (0.0 to 100.0)
    - rainfall_mm: float (recorded rainfall last 24h)
    - rainfall_forecast_24h_mm: float (forecast for next 24h)
    - is_simulated: int (1 for simulated academic data, 0 for hardware IoT)
    - metadata: dict (optional extensibility fields)

    Returns:
        Inserted document ObjectId string on success, or None on failure.
    """
    # Domain validation
    if not isinstance(farm_id, int) or farm_id <= 0:
        raise ValueError(f"farm_id must be a positive integer, got: {farm_id}")
    if not (0.0 <= soil_moisture_pct <= 100.0):
        raise ValueError(f"soil_moisture_pct ({soil_moisture_pct}) must be between 0.0 and 100.0")
    if not (0.0 <= humidity_pct <= 100.0):
        raise ValueError(f"humidity_pct ({humidity_pct}) must be between 0.0 and 100.0")
    if rainfall_mm < 0.0:
        raise ValueError(f"rainfall_mm ({rainfall_mm}) cannot be negative")

    coll = get_sensor_collection()
    if coll is None:
        return None

    # Standardize timestamp to ISO string
    if timestamp is None:
        ts_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(timestamp, datetime.datetime):
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    else:
        ts_str = str(timestamp).strip()

    forecast_val = rainfall_forecast_24h_mm if rainfall_forecast_24h_mm is not None else 0.0

    doc = {
        "farm_id": int(farm_id),
        "timestamp": ts_str,
        "soil_moisture_pct": round(float(soil_moisture_pct), 2),
        "soil_temperature_c": round(float(soil_temperature_c), 2),
        "humidity_pct": round(float(humidity_pct), 2),
        "rainfall_mm": round(float(rainfall_mm), 2),
        "rainfall_forecast_24h_mm": round(float(forecast_val), 2),
        "is_simulated": int(is_simulated),
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    if metadata and isinstance(metadata, dict):
        doc["metadata"] = metadata

    try:
        result = coll.insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:
        print(f"[mongodb_manager] Insert error: {e}")
        return None


def get_sensor_readings(
    farm_id: Optional[int] = None,
    start_date: Optional[Union[str, datetime.date, datetime.datetime]] = None,
    end_date: Optional[Union[str, datetime.date, datetime.datetime]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Read: Fetches telemetry documents from MongoDB filtered by farm_id and date range.
    Converts MongoDB '_id' into a JSON/display-friendly string.

    Returns:
        List of document dictionaries sorted chronologically descending.
    """
    coll = get_sensor_collection()
    if coll is None:
        return []

    query: Dict[str, Any] = {}

    if farm_id is not None:
        try:
            query["farm_id"] = int(farm_id)
        except (ValueError, TypeError):
            pass

    # Date range filters on ISO timestamp string
    date_filter: Dict[str, str] = {}
    if start_date:
        s_str = start_date.strftime("%Y-%m-%d 00:00:00") if hasattr(start_date, "strftime") else f"{str(start_date).strip()[:10]} 00:00:00"
        date_filter["$gte"] = s_str
    if end_date:
        e_str = end_date.strftime("%Y-%m-%d 23:59:59") if hasattr(end_date, "strftime") else f"{str(end_date).strip()[:10]} 23:59:59"
        date_filter["$lte"] = e_str

    if date_filter:
        query["timestamp"] = date_filter

    try:
        cursor = coll.find(query).sort("timestamp", pymongo.DESCENDING).limit(max(1, int(limit)))
        results: List[Dict[str, Any]] = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results
    except Exception as e:
        print(f"[mongodb_manager] Read error: {e}")
        return []


def get_latest_sensor_reading(farm_id: int) -> Optional[Dict[str, Any]]:
    """
    Read (Single): Fetches the most recent telemetry document for a specific farm.
    """
    readings = get_sensor_readings(farm_id=farm_id, limit=1)
    return readings[0] if readings else None


def update_sensor_reading(
    reading_id: str,
    update_data: Dict[str, Any],
) -> bool:
    """
    Update: Safely updates designated fields of an existing sensor reading document.

    Permitted mutable fields:
    - soil_moisture_pct
    - soil_temperature_c
    - humidity_pct
    - rainfall_mm
    - rainfall_forecast_24h_mm
    - is_simulated
    - metadata

    Returns:
        True if document was located and modified; False otherwise.
    """
    if not reading_id or not update_data:
        return False

    coll = get_sensor_collection()
    if coll is None:
        return False

    # Build safe $set dictionary
    safe_fields = {
        "soil_moisture_pct",
        "soil_temperature_c",
        "humidity_pct",
        "rainfall_mm",
        "rainfall_forecast_24h_mm",
        "is_simulated",
        "metadata",
    }
    set_dict: Dict[str, Any] = {}

    for k, v in update_data.items():
        if k in safe_fields:
            if k == "soil_moisture_pct" and not (0.0 <= float(v) <= 100.0):
                raise ValueError("soil_moisture_pct must be between 0.0 and 100.0")
            if k == "humidity_pct" and not (0.0 <= float(v) <= 100.0):
                raise ValueError("humidity_pct must be between 0.0 and 100.0")
            if k == "rainfall_mm" and float(v) < 0.0:
                raise ValueError("rainfall_mm cannot be negative")
            set_dict[k] = v

    if not set_dict:
        return False

    set_dict["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"

    # Match by ObjectId if possible, or string ID fallback
    match_query: Dict[str, Any]
    if ObjectId and ObjectId.is_valid(reading_id):
        match_query = {"_id": ObjectId(reading_id)}
    else:
        match_query = {"_id": reading_id}

    try:
        res = coll.update_one(match_query, {"$set": set_dict})
        return res.matched_count > 0
    except Exception as e:
        print(f"[mongodb_manager] Update error: {e}")
        return False


def delete_sensor_reading(reading_id: str) -> bool:
    """
    Delete: Safely deletes a specific test sensor reading by ID.

    Returns:
        True if document was found and deleted; False otherwise.
    """
    if not reading_id:
        return False

    coll = get_sensor_collection()
    if coll is None:
        return False

    match_query: Dict[str, Any]
    if ObjectId and ObjectId.is_valid(reading_id):
        match_query = {"_id": ObjectId(reading_id)}
    else:
        match_query = {"_id": reading_id}

    try:
        res = coll.delete_one(match_query)
        return res.deleted_count > 0
    except Exception as e:
        print(f"[mongodb_manager] Delete error: {e}")
        return False


def count_sensor_readings(farm_id: Optional[int] = None) -> int:
    """
    Counts total sensor readings in the collection, optionally filtered by farm_id.
    """
    coll = get_sensor_collection()
    if coll is None:
        return 0

    query = {"farm_id": int(farm_id)} if farm_id is not None else {}
    try:
        return coll.count_documents(query)
    except Exception:
        return 0


def get_telemetry_aggregation(farm_id: int) -> Dict[str, Any]:
    """
    Runs a NoSQL Aggregation Pipeline computing average, min, and max telemetry
    for a target farm from the MongoDB sensor_readings collection.
    """
    coll = get_sensor_collection()
    if coll is None:
        return {}

    pipeline = [
        {"$match": {"farm_id": int(farm_id)}},
        {
            "$group": {
                "_id": "$farm_id",
                "avg_moisture": {"$avg": "$soil_moisture_pct"},
                "min_moisture": {"$min": "$soil_moisture_pct"},
                "max_moisture": {"$max": "$soil_moisture_pct"},
                "avg_temp": {"$avg": "$soil_temperature_c"},
                "avg_humidity": {"$avg": "$humidity_pct"},
                "total_rain": {"$sum": "$rainfall_mm"},
                "count": {"$sum": 1},
            }
        },
    ]

    try:
        results = list(coll.aggregate(pipeline))
        if results:
            agg = results[0]
            agg.pop("_id", None)
            return {
                "avg_moisture": round(agg.get("avg_moisture", 0.0), 1),
                "min_moisture": round(agg.get("min_moisture", 0.0), 1),
                "max_moisture": round(agg.get("max_moisture", 0.0), 1),
                "avg_temp": round(agg.get("avg_temp", 0.0), 1),
                "avg_humidity": round(agg.get("avg_humidity", 0.0), 1),
                "total_rain": round(agg.get("total_rain", 0.0), 1),
                "count": agg.get("count", 0),
            }
        return {}
    except Exception as e:
        print(f"[mongodb_manager] Aggregation error: {e}")
        return {}


# =====================================================================
# PART 3: ADVANCED MONGODB AGGREGATION PIPELINES
# =====================================================================

def execute_pipeline(pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Executes a structured MongoDB aggregation pipeline against the 'sensor_readings' collection.
    Builds on Python dictionaries/lists with zero unsafe string concatenation.
    Safely serializes ObjectIds to strings and handles empty collections or database errors gracefully.
    """
    if not isinstance(pipeline, list):
        raise TypeError(f"Pipeline must be a list of stage dictionaries, got: {type(pipeline).__name__}")

    coll = get_sensor_collection()
    if coll is None:
        return []

    try:
        cursor = coll.aggregate(pipeline, allowDiskUse=True)
        results: List[Dict[str, Any]] = []
        for doc in cursor:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results
    except Exception as e:
        print(f"[mongodb_manager] Pipeline execution error: {e}")
        raise e


def build_pipeline_match(
    farm_id: Optional[int] = None,
    start_date: Optional[Union[str, datetime.date]] = None,
    end_date: Optional[Union[str, datetime.date]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Pipeline 1 ($MATCH + $SORT):
    Filters readings for a selected farm plot and optional ISO date range.
    """
    match_stage: Dict[str, Any] = {}
    if farm_id is not None:
        match_stage["farm_id"] = int(farm_id)

    date_filter: Dict[str, str] = {}
    if start_date:
        s_str = start_date.strftime("%Y-%m-%d 00:00:00") if hasattr(start_date, "strftime") else f"{str(start_date).strip()[:10]} 00:00:00"
        date_filter["$gte"] = s_str
    if end_date:
        e_str = end_date.strftime("%Y-%m-%d 23:59:59") if hasattr(end_date, "strftime") else f"{str(end_date).strip()[:10]} 23:59:59"
        date_filter["$lte"] = e_str

    if date_filter:
        match_stage["timestamp"] = date_filter

    pipeline: List[Dict[str, Any]] = []
    if match_stage:
        pipeline.append({"$match": match_stage})

    pipeline.append({"$sort": {"timestamp": -1}})
    pipeline.append({"$limit": max(1, int(limit))})
    return pipeline


def build_pipeline_group(farm_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Pipeline 2 ($GROUP):
    Calculates average soil moisture, average temperature, maximum rainfall,
    and total reading count.
    """
    pipeline: List[Dict[str, Any]] = []
    if farm_id is not None:
        pipeline.append({"$match": {"farm_id": int(farm_id)}})

    group_id = "$farm_id" if farm_id is None else None
    pipeline.append({
        "$group": {
            "_id": group_id,
            "reading_count": {"$sum": 1},
            "avg_moisture": {"$avg": "$soil_moisture_pct"},
            "avg_temperature": {"$avg": "$soil_temperature_c"},
            "avg_humidity": {"$avg": "$humidity_pct"},
            "max_rainfall": {"$max": "$rainfall_mm"},
            "min_moisture": {"$min": "$soil_moisture_pct"},
            "max_moisture": {"$max": "$soil_moisture_pct"},
        }
    })
    pipeline.append({
        "$project": {
            "_id": 1,
            "reading_count": 1,
            "avg_moisture": {"$round": ["$avg_moisture", 2]},
            "avg_temperature": {"$round": ["$avg_temperature", 2]},
            "avg_humidity": {"$round": ["$avg_humidity", 2]},
            "max_rainfall": {"$round": ["$max_rainfall", 2]},
            "min_moisture": {"$round": ["$min_moisture", 2]},
            "max_moisture": {"$round": ["$max_moisture", 2]},
        }
    })
    return pipeline


def build_pipeline_sort(
    farm_id: Optional[int] = None,
    sort_field: str = "timestamp",
    ascending: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Pipeline 3 ($SORT):
    Demonstrates sorting by timestamp, moisture, temperature, or rainfall.
    """
    valid_fields = {"timestamp", "soil_moisture_pct", "soil_temperature_c", "humidity_pct", "rainfall_mm"}
    clean_field = sort_field if sort_field in valid_fields else "timestamp"
    direction = 1 if ascending else -1

    pipeline: List[Dict[str, Any]] = []
    if farm_id is not None:
        pipeline.append({"$match": {"farm_id": int(farm_id)}})

    pipeline.append({"$sort": {clean_field: direction}})
    pipeline.append({"$limit": max(1, int(limit))})
    return pipeline


def build_pipeline_project(
    farm_id: Optional[int] = None,
    target_threshold: float = 35.0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Pipeline 4 ($PROJECT):
    Projects only specified fields and calculates derived values:
    - Formats timestamp substring
    - Computes deficit against target_threshold
    - Classifies status (Adequate vs Deficit)
    """
    pipeline: List[Dict[str, Any]] = []
    if farm_id is not None:
        pipeline.append({"$match": {"farm_id": int(farm_id)}})

    pipeline.append({"$sort": {"timestamp": -1}})
    pipeline.append({"$limit": max(1, int(limit))})
    pipeline.append({
        "$project": {
            "farm_id": 1,
            "timestamp": 1,
            "soil_moisture_pct": 1,
            "soil_temperature_c": 1,
            "humidity_pct": 1,
            "moisture_deficit_pct": {
                "$round": [{"$subtract": [float(target_threshold), "$soil_moisture_pct"]}, 2]
            },
            "status": {
                "$cond": {
                    "if": {"$gte": ["$soil_moisture_pct", float(target_threshold)]},
                    "then": "ADEQUATE",
                    "else": "DEFICIT",
                }
            },
        }
    })
    return pipeline


def build_pipeline_daily_aggregation(
    farm_id: Optional[int] = None,
    limit_days: int = 14,
) -> List[Dict[str, Any]]:
    """
    Pipeline 5 (DAILY AGGREGATION):
    Groups sensor telemetry by calendar day, calculating average moisture,
    average temperature, and total/max rainfall.
    """
    pipeline: List[Dict[str, Any]] = []
    if farm_id is not None:
        pipeline.append({"$match": {"farm_id": int(farm_id)}})

    # Extract YYYY-MM-DD from ISO timestamp string
    pipeline.append({
        "$project": {
            "day": {"$substrCP": ["$timestamp", 0, 10]},
            "farm_id": 1,
            "soil_moisture_pct": 1,
            "soil_temperature_c": 1,
            "rainfall_mm": 1,
            "humidity_pct": 1,
        }
    })
    pipeline.append({
        "$group": {
            "_id": "$day",
            "readings_count": {"$sum": 1},
            "avg_moisture": {"$avg": "$soil_moisture_pct"},
            "avg_temperature": {"$avg": "$soil_temperature_c"},
            "avg_humidity": {"$avg": "$humidity_pct"},
            "total_rainfall": {"$sum": "$rainfall_mm"},
            "max_rainfall": {"$max": "$rainfall_mm"},
        }
    })
    pipeline.append({
        "$project": {
            "calendar_day": "$_id",
            "_id": 0,
            "readings_count": 1,
            "avg_moisture": {"$round": ["$avg_moisture", 2]},
            "avg_temperature": {"$round": ["$avg_temperature", 2]},
            "avg_humidity": {"$round": ["$avg_humidity", 2]},
            "total_rainfall": {"$round": ["$total_rainfall", 2]},
            "max_rainfall": {"$round": ["$max_rainfall", 2]},
        }
    })
    pipeline.append({"$sort": {"calendar_day": -1}})
    pipeline.append({"$limit": max(1, int(limit_days))})
    return pipeline


def build_pipeline_moisture_categories(
    farm_id: Optional[int] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Pipeline 6 (MOISTURE CATEGORIES):
    Categorizes readings into configurable moisture ranges:
    - Critical Drought (<20%)
    - Needs Water (20-40%)
    - Moderate (40-60%)
    - Optimal (60-80%)
    - Saturated (>=80%)

    NOTE: These thresholds are academic demonstration boundaries and vary
    widely depending on crop transpiration demand and soil texture.
    """
    th = thresholds or {
        "drought": 20.0,
        "needs_water": 40.0,
        "moderate": 60.0,
        "optimal": 80.0,
    }

    pipeline: List[Dict[str, Any]] = []
    if farm_id is not None:
        pipeline.append({"$match": {"farm_id": int(farm_id)}})

    pipeline.append({
        "$project": {
            "farm_id": 1,
            "soil_moisture_pct": 1,
            "category": {
                "$switch": {
                    "branches": [
                        {"case": {"$lt": ["$soil_moisture_pct", float(th["drought"])]}, "then": "1. Critical Drought (<20%)"},
                        {"case": {"$lt": ["$soil_moisture_pct", float(th["needs_water"])]}, "then": "2. Needs Water (20–40%)"},
                        {"case": {"$lt": ["$soil_moisture_pct", float(th["moderate"])]}, "then": "3. Moderate (40–60%)"},
                        {"case": {"$lt": ["$soil_moisture_pct", float(th["optimal"])]}, "then": "4. Optimal (60–80%)"},
                    ],
                    "default": "5. Saturated (≥80%)",
                }
            },
        }
    })
    pipeline.append({
        "$group": {
            "_id": "$category",
            "reading_count": {"$sum": 1},
            "avg_moisture": {"$avg": "$soil_moisture_pct"},
            "min_moisture": {"$min": "$soil_moisture_pct"},
            "max_moisture": {"$max": "$soil_moisture_pct"},
        }
    })
    pipeline.append({
        "$project": {
            "category": "$_id",
            "_id": 0,
            "reading_count": 1,
            "avg_moisture": {"$round": ["$avg_moisture", 2]},
            "min_moisture": {"$round": ["$min_moisture", 2]},
            "max_moisture": {"$round": ["$max_moisture", 2]},
        }
    })
    pipeline.append({"$sort": {"category": 1}})
    return pipeline


def build_pipeline_farm_comparison() -> List[Dict[str, Any]]:
    """
    Pipeline 7 (FARM COMPARISON):
    Compares average soil moisture, temperature, rainfall, and reading counts
    across all registered farms.
    """
    pipeline: List[Dict[str, Any]] = [
        {
            "$group": {
                "_id": "$farm_id",
                "farm_id": {"$first": "$farm_id"},
                "total_readings": {"$sum": 1},
                "avg_moisture": {"$avg": "$soil_moisture_pct"},
                "min_moisture": {"$min": "$soil_moisture_pct"},
                "max_moisture": {"$max": "$soil_moisture_pct"},
                "avg_temperature": {"$avg": "$soil_temperature_c"},
                "avg_humidity": {"$avg": "$humidity_pct"},
                "total_rainfall": {"$sum": "$rainfall_mm"},
                "latest_telemetry_time": {"$max": "$timestamp"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "farm_id": 1,
                "total_readings": 1,
                "avg_moisture": {"$round": ["$avg_moisture", 2]},
                "min_moisture": {"$round": ["$min_moisture", 2]},
                "max_moisture": {"$round": ["$max_moisture", 2]},
                "avg_temperature": {"$round": ["$avg_temperature", 2]},
                "avg_humidity": {"$round": ["$avg_humidity", 2]},
                "total_rainfall": {"$round": ["$total_rainfall", 2]},
                "latest_telemetry_time": 1,
            }
        },
        {"$sort": {"farm_id": 1}},
    ]
    return pipeline


def build_pipeline_unwind(farm_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Pipeline 8 ($UNWIND Array Processing):
    Demonstrates array processing on nested multi-depth sensor probe arrays
    ('probe_nodes' or 'diagnostic_alerts').

    Document Schema for Array Telemetry:
    {
        "farm_id": 1,
        "timestamp": "2026-10-24 12:00:00",
        "probe_nodes": [
            {"node_id": "P15", "depth_cm": 15, "moisture_pct": 32.0},
            {"node_id": "P30", "depth_cm": 30, "moisture_pct": 38.5},
            {"node_id": "P60", "depth_cm": 60, "moisture_pct": 46.0}
        ]
    }
    """
    pipeline: List[Dict[str, Any]] = []
    if farm_id is not None:
        pipeline.append({"$match": {"farm_id": int(farm_id)}})

    # Filter for documents containing the probe_nodes array
    pipeline.append({"$match": {"probe_nodes": {"$exists": True, "$type": "array"}}})
    pipeline.append({"$unwind": "$probe_nodes"})
    pipeline.append({
        "$group": {
            "_id": {
                "depth_cm": "$probe_nodes.depth_cm",
                "node_id": "$probe_nodes.node_id",
            },
            "sample_count": {"$sum": 1},
            "avg_depth_moisture": {"$avg": "$probe_nodes.moisture_pct"},
            "min_depth_moisture": {"$min": "$probe_nodes.moisture_pct"},
            "max_depth_moisture": {"$max": "$probe_nodes.moisture_pct"},
        }
    })
    pipeline.append({
        "$project": {
            "_id": 0,
            "node_id": "$_id.node_id",
            "depth_cm": "$_id.depth_cm",
            "sample_count": 1,
            "avg_depth_moisture": {"$round": ["$avg_depth_moisture", 2]},
            "min_depth_moisture": {"$round": ["$min_depth_moisture", 2]},
            "max_depth_moisture": {"$round": ["$max_depth_moisture", 2]},
        }
    })
    pipeline.append({"$sort": {"depth_cm": 1}})
    return pipeline


def seed_sample_array_telemetry(farm_id: int = 1) -> bool:
    """
    Seeds a sample document with array fields ('probe_nodes') to enable live testing
    of the $UNWIND pipeline demonstration.
    """
    coll = get_sensor_collection()
    if coll is None:
        return False

    sample_doc = {
        "farm_id": int(farm_id),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "soil_moisture_pct": 35.0,
        "soil_temperature_c": 28.0,
        "humidity_pct": 65.0,
        "rainfall_mm": 0.0,
        "rainfall_forecast_24h_mm": 5.0,
        "is_simulated": 1,
        "probe_nodes": [
            {"node_id": "P15-RootTop", "depth_cm": 15, "moisture_pct": 28.5},
            {"node_id": "P30-RootMid", "depth_cm": 30, "moisture_pct": 36.0},
            {"node_id": "P60-RootDeep", "depth_cm": 60, "moisture_pct": 44.2},
        ],
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }

    try:
        coll.insert_one(sample_doc)
        return True
    except Exception as e:
        print(f"[mongodb_manager] Seed array telemetry error: {e}")
        return False

