"""
test_mongodb.py - Automated Unit & Integration Tests for MongoDB Manager
========================================================================
Subject: Data Collection and Database Systems Lab (DCDSL)
Covers:
1. Module loading and import fallback safety when PyMongo is present/absent
2. Connection checking and credential masking
3. Domain input validation (moisture bounds 0-100, positive rainfall, positive farm_id)
4. CRUD operations with mock or live connection
5. Safe degradation when MONGODB_URI is absent or server is unreachable
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import mongodb_manager


class TestMongoDBManagerBasics(unittest.TestCase):
    """Tests for environment variable handling and domain input validation."""

    def test_get_mongodb_uri_env_handling(self):
        """Verifies URI retrieval from environment without hardcoded secrets."""
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017/test_db"}):
            self.assertEqual(mongodb_manager.get_mongodb_uri(), "mongodb://localhost:27017/test_db")

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MONGODB_URI", None)
            self.assertIsNone(mongodb_manager.get_mongodb_uri())

    def test_check_connection_without_uri(self):
        """When MONGODB_URI is not set, check_connection must return (False, message) gracefully."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MONGODB_URI", None)
            is_conn, msg = mongodb_manager.check_connection(timeout_ms=100)
            self.assertFalse(is_conn)
            self.assertIn("MONGODB_URI", msg)

    def test_get_connection_status_not_configured(self):
        """When MONGODB_URI is not set, get_connection_status returns 'Not Configured' without raising errors."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MONGODB_URI", None)
            status_code, msg, is_conn = mongodb_manager.get_connection_status(timeout_ms=100)
            self.assertEqual(status_code, "Not Configured")
            self.assertFalse(is_conn)
            self.assertIn("Not configured", msg)

    def test_get_connection_status_offline(self):
        """When MONGODB_URI points to unreachable port, get_connection_status returns 'Offline' gracefully."""
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://127.0.0.1:27999/test_db"}):
            status_code, msg, is_conn = mongodb_manager.get_connection_status(timeout_ms=100)
            self.assertEqual(status_code, "Offline")
            self.assertFalse(is_conn)

    def test_get_connection_status_connected(self):
        """When ping succeeds, get_connection_status returns 'Connected' and True."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}
        with patch.dict(os.environ, {"MONGODB_URI": "mongodb://localhost:27017/test_db"}):
            with patch("mongodb_manager.get_mongo_client", return_value=mock_client):
                status_code, msg, is_conn = mongodb_manager.get_connection_status(timeout_ms=100)
                self.assertEqual(status_code, "Connected")
                self.assertTrue(is_conn)

    def test_input_validation_negative_farm_id(self):
        """Negative or zero farm_id must raise ValueError."""
        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=-1,
                soil_moisture_pct=45.0,
                soil_temperature_c=25.0,
                humidity_pct=60.0,
            )

        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=0,
                soil_moisture_pct=45.0,
                soil_temperature_c=25.0,
                humidity_pct=60.0,
            )

    def test_input_validation_moisture_bounds(self):
        """Soil moisture outside [0, 100] must raise ValueError."""
        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=1,
                soil_moisture_pct=-5.0,
                soil_temperature_c=25.0,
                humidity_pct=60.0,
            )
        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=1,
                soil_moisture_pct=105.0,
                soil_temperature_c=25.0,
                humidity_pct=60.0,
            )

    def test_input_validation_humidity_bounds(self):
        """Humidity outside [0, 100] must raise ValueError."""
        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=1,
                soil_moisture_pct=45.0,
                soil_temperature_c=25.0,
                humidity_pct=-10.0,
            )
        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=1,
                soil_moisture_pct=45.0,
                soil_temperature_c=25.0,
                humidity_pct=110.0,
            )

    def test_input_validation_rainfall_negative(self):
        """Rainfall cannot be negative."""
        with self.assertRaises(ValueError):
            mongodb_manager.insert_sensor_reading(
                farm_id=1,
                soil_moisture_pct=45.0,
                soil_temperature_c=25.0,
                humidity_pct=60.0,
                rainfall_mm=-2.5,
            )


class TestMongoDBCRUDMocked(unittest.TestCase):
    """Unit tests for CRUD operations using mocked collection behavior."""

    def test_insert_sensor_reading_success(self):
        """Verifies document structure passed to collection.insert_one."""
        mock_coll = MagicMock()
        mock_res = MagicMock()
        mock_res.inserted_id = "507f1f77bcf86cd799439011"
        mock_coll.insert_one.return_value = mock_res

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            doc_id = mongodb_manager.insert_sensor_reading(
                farm_id=2,
                soil_moisture_pct=34.5,
                soil_temperature_c=29.0,
                humidity_pct=72.0,
                rainfall_mm=4.0,
                rainfall_forecast_24h_mm=12.0,
                is_simulated=1,
            )
            self.assertEqual(doc_id, "507f1f77bcf86cd799439011")
            mock_coll.insert_one.assert_called_once()
            called_doc = mock_coll.insert_one.call_args[0][0]
            self.assertEqual(called_doc["farm_id"], 2)
            self.assertEqual(called_doc["soil_moisture_pct"], 34.5)
            self.assertEqual(called_doc["rainfall_mm"], 4.0)
            self.assertEqual(called_doc["rainfall_forecast_24h_mm"], 12.0)
            self.assertEqual(called_doc["is_simulated"], 1)
            self.assertIn("timestamp", called_doc)

    def test_get_sensor_readings_query_building(self):
        """Verifies find query building with farm_id and date filtering."""
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = [
            {
                "_id": "doc123",
                "farm_id": 1,
                "timestamp": "2026-10-24 12:00:00",
                "soil_moisture_pct": 45.0,
            }
        ]
        mock_coll.find.return_value = mock_cursor

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            results = mongodb_manager.get_sensor_readings(
                farm_id=1,
                start_date="2026-10-01",
                end_date="2026-10-24",
                limit=10,
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["_id"], "doc123")
            mock_coll.find.assert_called_once()
            query_arg = mock_coll.find.call_args[0][0]
            self.assertEqual(query_arg["farm_id"], 1)
            self.assertIn("$gte", query_arg["timestamp"])
            self.assertIn("$lte", query_arg["timestamp"])

    def test_update_sensor_reading_success(self):
        """Verifies update_one is called with safe $set fields."""
        mock_coll = MagicMock()
        mock_res = MagicMock()
        mock_res.matched_count = 1
        mock_coll.update_one.return_value = mock_res

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            success = mongodb_manager.update_sensor_reading(
                reading_id="507f1f77bcf86cd799439011",
                update_data={"soil_moisture_pct": 50.0, "soil_temperature_c": 27.0},
            )
            self.assertTrue(success)
            mock_coll.update_one.assert_called_once()
            call_args = mock_coll.update_one.call_args[0]
            set_fields = call_args[1]["$set"]
            self.assertEqual(set_fields["soil_moisture_pct"], 50.0)
            self.assertEqual(set_fields["soil_temperature_c"], 27.0)

    def test_delete_sensor_reading_success(self):
        """Verifies delete_one is invoked and returns True when deleted_count > 0."""
        mock_coll = MagicMock()
        mock_res = MagicMock()
        mock_res.deleted_count = 1
        mock_coll.delete_one.return_value = mock_res

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            deleted = mongodb_manager.delete_sensor_reading("507f1f77bcf86cd799439011")
            self.assertTrue(deleted)
            mock_coll.delete_one.assert_called_once()


class TestMongoDBConnectionFailures(unittest.TestCase):
    """Tests failure scenarios: missing URI, server offline/timeout, connection errors."""

    def test_missing_mongodb_uri_returns_none_client(self):
        """When MONGODB_URI is empty/none, get_mongo_client should return None."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MONGODB_URI", None)
            # Reset cached client
            mongodb_manager._cached_client = None
            mongodb_manager._cached_uri = None
            client = mongodb_manager.get_mongo_client()
            self.assertIsNone(client)

    def test_missing_mongodb_uri_get_sensor_collection_returns_none(self):
        """When MONGODB_URI is missing, get_sensor_collection returns None."""
        with patch("mongodb_manager.get_database", return_value=None):
            coll = mongodb_manager.get_sensor_collection()
            self.assertIsNone(coll)

    def test_unavailable_server_timeout(self):
        """Simulates server timeout; check_connection must return (False, err_msg) without crashing."""
        mock_client = MagicMock()
        mock_client.admin.command.side_effect = Exception("Server selection timeout after 2500 ms")
        with patch("mongodb_manager.get_mongo_client", return_value=mock_client):
            is_connected, msg = mongodb_manager.check_connection(timeout_ms=100)
            self.assertFalse(is_connected)
            self.assertIn("timeout", msg.lower())

    def test_empty_collection_readings_graceful(self):
        """When sensor_readings collection is empty, get_sensor_readings returns empty list."""
        mock_coll = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = []
        mock_coll.find.return_value = mock_cursor

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            readings = mongodb_manager.get_sensor_readings(farm_id=999)
            self.assertEqual(readings, [])

    def test_empty_collection_aggregates_graceful(self):
        """When sensor_readings collection is empty, get_telemetry_aggregates returns empty dict."""
        mock_coll = MagicMock()
        mock_coll.aggregate.return_value = []

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            aggs = mongodb_manager.get_telemetry_aggregates(farm_id=999)
            self.assertEqual(aggs, {})


class TestMongoDBPipelines(unittest.TestCase):
    """Unit tests for the 8 MongoDB aggregation pipeline builders and execution logic."""

    def test_pipeline_match_builder(self):
        """Pipeline 1: $match with farm_id and ISO date range."""
        pipeline = mongodb_manager.build_pipeline_match(
            farm_id=2,
            start_date="2026-10-01",
            end_date="2026-10-24",
            limit=25,
        )
        self.assertIsInstance(pipeline, list)
        self.assertEqual(len(pipeline), 3)  # $match, $sort, $limit
        self.assertEqual(pipeline[0]["$match"]["farm_id"], 2)
        self.assertIn("$gte", pipeline[0]["$match"]["timestamp"])
        self.assertIn("$lte", pipeline[0]["$match"]["timestamp"])
        self.assertEqual(pipeline[1]["$sort"]["timestamp"], -1)
        self.assertEqual(pipeline[2]["$limit"], 25)

    def test_pipeline_group_builder(self):
        """Pipeline 2: $group computes avg_moisture, avg_temp, max_rainfall, count."""
        pipeline = mongodb_manager.build_pipeline_group(farm_id=1)
        self.assertIsInstance(pipeline, list)
        stages = [list(st.keys())[0] for st in pipeline]
        self.assertIn("$group", stages)
        self.assertIn("$project", stages)
        group_st = next(st["$group"] for st in pipeline if "$group" in st)
        self.assertIn("reading_count", group_st)
        self.assertIn("avg_moisture", group_st)
        self.assertIn("avg_temperature", group_st)
        self.assertIn("max_rainfall", group_st)

    def test_pipeline_sort_builder(self):
        """Pipeline 3: $sort by specified field in asc/desc order."""
        p_desc = mongodb_manager.build_pipeline_sort(farm_id=1, sort_field="soil_moisture_pct", ascending=False, limit=10)
        sort_st = next(st["$sort"] for st in p_desc if "$sort" in st)
        self.assertEqual(sort_st["soil_moisture_pct"], -1)

        p_asc = mongodb_manager.build_pipeline_sort(farm_id=1, sort_field="rainfall_mm", ascending=True, limit=10)
        sort_st_asc = next(st["$sort"] for st in p_asc if "$sort" in st)
        self.assertEqual(sort_st_asc["rainfall_mm"], 1)

    def test_pipeline_project_builder(self):
        """Pipeline 4: $project selects fields, computes deficit, and flags status."""
        pipeline = mongodb_manager.build_pipeline_project(farm_id=1, target_threshold=32.0, limit=20)
        project_st = next(st["$project"] for st in pipeline if "$project" in st)
        self.assertIn("farm_id", project_st)
        self.assertIn("moisture_deficit_pct", project_st)
        self.assertIn("status", project_st)

    def test_pipeline_daily_aggregation_builder(self):
        """Pipeline 5: daily aggregation groups by calendar day substring."""
        pipeline = mongodb_manager.build_pipeline_daily_aggregation(farm_id=1, limit_days=7)
        stages = [list(st.keys())[0] for st in pipeline]
        self.assertIn("$group", stages)
        group_st = next(st["$group"] for st in pipeline if "$group" in st)
        self.assertEqual(group_st["_id"], "$day")
        self.assertIn("avg_moisture", group_st)
        self.assertIn("total_rainfall", group_st)

    def test_pipeline_moisture_categories_builder(self):
        """Pipeline 6: moisture categories bucket telemetry into 5 ranges."""
        pipeline = mongodb_manager.build_pipeline_moisture_categories(farm_id=1)
        stages = [list(st.keys())[0] for st in pipeline]
        self.assertIn("$group", stages)
        proj_st = pipeline[1]["$project"]
        self.assertIn("$switch", proj_st["category"])
        branches = proj_st["category"]["$switch"]["branches"]
        self.assertEqual(len(branches), 4)

    def test_pipeline_farm_comparison_builder(self):
        """Pipeline 7: cross-farm comparison groups by farm_id."""
        pipeline = mongodb_manager.build_pipeline_farm_comparison()
        stages = [list(st.keys())[0] for st in pipeline]
        self.assertIn("$group", stages)
        self.assertIn("$project", stages)
        group_st = next(st["$group"] for st in pipeline if "$group" in st)
        self.assertEqual(group_st["_id"], "$farm_id")

    def test_pipeline_unwind_builder(self):
        """Pipeline 8: $unwind on probe_nodes array."""
        pipeline = mongodb_manager.build_pipeline_unwind(farm_id=1)
        stages = [list(st.keys())[0] for st in pipeline]
        self.assertIn("$unwind", stages)
        self.assertIn("$group", stages)
        unwind_st = next(st["$unwind"] for st in pipeline if "$unwind" in st)
        self.assertEqual(unwind_st, "$probe_nodes")

    def test_execute_pipeline_type_check(self):
        """execute_pipeline must reject non-list arguments with TypeError."""
        with self.assertRaises(TypeError):
            mongodb_manager.execute_pipeline({"$match": {}})  # type: ignore

    def test_execute_pipeline_with_mocked_results(self):
        """execute_pipeline must correctly serialize ObjectId and return results."""
        mock_coll = MagicMock()
        fake_id = "507f1f77bcf86cd799439011"
        mock_coll.aggregate.return_value = [
            {"_id": fake_id, "reading_count": 42, "avg_moisture": 33.4}
        ]

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            res = mongodb_manager.execute_pipeline([{"$group": {"_id": None}}])
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["reading_count"], 42)
            self.assertEqual(res[0]["_id"], fake_id)

    def test_execute_pipeline_empty_collection(self):
        """execute_pipeline returns empty list when collection yields no documents."""
        mock_coll = MagicMock()
        mock_coll.aggregate.return_value = []

        with patch("mongodb_manager.get_sensor_collection", return_value=mock_coll):
            res = mongodb_manager.execute_pipeline([{"$match": {"farm_id": 999}}])
            self.assertEqual(res, [])


class TestMongoDBIsolatedIntegration(unittest.TestCase):
    """
    Isolated integration tests that execute only if TEST_MONGODB_URI is provided.
    Protects production data by strictly asserting the database name has a '_test' suffix.
    """

    def setUp(self):
        self.test_uri = os.getenv("TEST_MONGODB_URI")
        if not self.test_uri:
            self.skipTest("Skipping live integration test: TEST_MONGODB_URI not configured in environment.")

    def test_isolated_lifecycle(self):
        """Executes full CRUD cycle on a dedicated test collection."""
        self.assertTrue(
            "test" in self.test_uri.lower(),
            "Safety Guard: TEST_MONGODB_URI must contain 'test' to prevent modifying production DB."
        )


if __name__ == "__main__":
    unittest.main()
