"""
test_irrigation.py - Automated Unit & Integration Tests
=======================================================
Covers:
1. Explainable rule-based recommendation logic in advisor.py
2. Database CRUD operations, constraints, and DCDSL analytical queries in db.py

Compatible with both `pytest` and `python3 -m unittest`.
"""

import os
import tempfile
import unittest
import sqlite3
import pandas as pd

import advisor
from advisor import calculate_irrigation_recommendation, RecommendationResult
import db


class TestAdvisorRecommendationLogic(unittest.TestCase):
    """Unit tests for the explainable rule-based advisor logic."""

    def test_critical_drought_recommendation(self):
        """Severely dry soil (<20%) must trigger CRITICAL urgency and positive dosage."""
        res = calculate_irrigation_recommendation(
            soil_moisture_pct=16.0,
            rainfall_forecast_24h_mm=0.0,
            crop_type="Tomato",
            area_acres=2.0,
            soil_type="Loamy",
        )
        self.assertEqual(res.status_code, "IRRIGATE")
        self.assertEqual(res.urgency, "CRITICAL")
        self.assertGreater(res.recommended_liters, 0.0)
        self.assertGreater(res.recommended_duration_min, 0)
        self.assertIn("R4_MOISTURE_DEFICIT_DETECTED", res.rules_fired)
        self.assertTrue(any("Wilting Point" in r for r in res.reasons))

    def test_moderate_deficit_recommendation(self):
        """Moisture below crop threshold (Tomato min: 35%) must trigger IRRIGATE."""
        res = calculate_irrigation_recommendation(
            soil_moisture_pct=28.0,
            rainfall_forecast_24h_mm=1.0,
            crop_type="Tomato",
            area_acres=1.0,
            soil_type="Loamy",
        )
        self.assertEqual(res.status_code, "IRRIGATE")
        self.assertIn(res.urgency, ["HIGH", "MODERATE"])
        self.assertGreater(res.recommended_liters, 0.0)

    def test_optimal_moisture_requires_zero_water(self):
        """Moisture above threshold must trigger OPTIMAL with 0 liters."""
        res = calculate_irrigation_recommendation(
            soil_moisture_pct=42.0,
            rainfall_forecast_24h_mm=0.0,
            crop_type="Wheat",  # min threshold: 30%
            area_acres=3.0,
            soil_type="Loamy",
        )
        self.assertEqual(res.status_code, "OPTIMAL")
        self.assertEqual(res.urgency, "NONE")
        self.assertEqual(res.recommended_liters, 0.0)
        self.assertEqual(res.recommended_duration_min, 0)
        self.assertIn("R3_MOISTURE_ADEQUATE", res.rules_fired)

    def test_heavy_rainfall_forecast_postponement(self):
        """Even with mild deficit, forecast >= 12mm rain must postpone irrigation to save water."""
        res = calculate_irrigation_recommendation(
            soil_moisture_pct=27.0,  # Below Tomato 35% threshold
            rainfall_forecast_24h_mm=18.0,  # Heavy rain predicted
            crop_type="Tomato",
            area_acres=2.0,
            soil_type="Loamy",
        )
        self.assertEqual(res.status_code, "POSTPONE_RAIN")
        self.assertEqual(res.recommended_liters, 0.0)
        self.assertIn("R2_HEAVY_RAIN_SUPPRESSION", res.rules_fired)
        self.assertTrue(any("Water Conservation Principle" in r for r in res.reasons))

    def test_waterlogging_saturation_protection(self):
        """Moisture >= 75% must trigger WATERLOG_RISK protection."""
        res = calculate_irrigation_recommendation(
            soil_moisture_pct=82.0,
            rainfall_forecast_24h_mm=0.0,
            crop_type="Rice",
            area_acres=5.0,
            soil_type="Clay",
        )
        self.assertEqual(res.status_code, "WATERLOG_RISK")
        self.assertEqual(res.recommended_liters, 0.0)
        self.assertIn("R1_WATERLOG_PROTECTION", res.rules_fired)

    def test_temperature_evapotranspiration_adjustment(self):
        """High heat (>=33°C) must recommend more water than standard temperature (25°C)."""
        res_normal = calculate_irrigation_recommendation(
            soil_moisture_pct=22.0,
            rainfall_forecast_24h_mm=0.0,
            soil_temperature_c=25.0,
            crop_type="Maize",
            area_acres=1.0,
        )
        res_hot = calculate_irrigation_recommendation(
            soil_moisture_pct=22.0,
            rainfall_forecast_24h_mm=0.0,
            soil_temperature_c=36.0,
            crop_type="Maize",
            area_acres=1.0,
        )
        self.assertGreater(res_hot.recommended_liters, res_normal.recommended_liters)
        self.assertIn("R6_HIGH_EVAPOTRANSPIRATION", res_hot.rules_fired)

    def test_soil_texture_multiplier(self):
        """Sandy soil (higher drainage) requires higher baseline dosage than Clay."""
        res_sandy = calculate_irrigation_recommendation(
            soil_moisture_pct=22.0,
            rainfall_forecast_24h_mm=0.0,
            crop_type="Wheat",
            area_acres=2.0,
            soil_type="Sandy",
        )
        res_clay = calculate_irrigation_recommendation(
            soil_moisture_pct=22.0,
            rainfall_forecast_24h_mm=0.0,
            crop_type="Wheat",
            area_acres=2.0,
            soil_type="Clay",
        )
        self.assertGreater(res_sandy.recommended_liters, res_clay.recommended_liters)

    def test_input_validation_errors(self):
        """Invalid inputs must raise ValueError."""
        with self.assertRaises(ValueError):
            calculate_irrigation_recommendation(-5.0, 0.0)  # negative moisture
        with self.assertRaises(ValueError):
            calculate_irrigation_recommendation(105.0, 0.0)  # moisture > 100
        with self.assertRaises(ValueError):
            calculate_irrigation_recommendation(30.0, -2.0)  # negative rain forecast
        with self.assertRaises(ValueError):
            calculate_irrigation_recommendation(30.0, 0.0, area_acres=0.0)  # zero area


class TestDatabaseOperations(unittest.TestCase):
    """Integration tests for SQLite schema, parameterized CRUD, and analytical queries."""

    @classmethod
    def setUpClass(cls):
        """Create a dedicated temporary database for isolated testing."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db_path = os.path.join(cls.temp_dir.name, "test_irrigation.db")
        db.init_database(db_path=cls.test_db_path)

    @classmethod
    def tearDownClass(cls):
        """Cleanup temporary files."""
        cls.temp_dir.cleanup()

    def test_database_initialization_and_farms_exist(self):
        """Verifies database initialized with sample farms."""
        farms = db.get_all_farms(db_path=self.test_db_path)
        self.assertGreaterEqual(len(farms), 5)
        self.assertEqual(farms[0]["name"], "Green Valley Agro")

    def test_init_database_safe_preserves_records(self):
        """Verifies that init_database_safe preserves existing records without dropping."""
        initial_farms = db.get_all_farms(db_path=self.test_db_path)
        count_before = len(initial_farms)

        # Call safe initialization on an existing populated database
        seeded = db.init_database_safe(db_path=self.test_db_path)
        self.assertFalse(seeded)  # Should return False indicating existing records were preserved

        # Ensure record count is identical
        farms_after = db.get_all_farms(db_path=self.test_db_path)
        self.assertEqual(len(farms_after), count_before)
        self.assertEqual(farms_after[0]["name"], initial_farms[0]["name"])


    def test_get_farm_by_id(self):
        """Parameterized lookup by farm_id."""
        farm = db.get_farm_by_id(1, db_path=self.test_db_path)
        self.assertIsNotNone(farm)
        self.assertEqual(farm["farm_id"], 1)
        self.assertEqual(farm["crop_type"], "Tomato")

        # Invalid ID tests
        with self.assertRaises(ValueError):
            db.get_farm_by_id(-1, db_path=self.test_db_path)

    def test_add_farm(self):
        """Verifies adding a new farm plot with input validation."""
        new_fid = db.add_farm(
            name="Orchard Green",
            owner_name="Devika Sen",
            location="Zone F",
            crop_type="Maize",
            area_acres=4.5,
            soil_type="Loamy",
            db_path=self.test_db_path,
        )
        self.assertIsInstance(new_fid, int)
        farm = db.get_farm_by_id(new_fid, db_path=self.test_db_path)
        self.assertEqual(farm["name"], "Orchard Green")

        with self.assertRaises(ValueError):
            db.add_farm("", "Owner", "Loc", "Maize", 2.0, "Loamy", db_path=self.test_db_path)


    def test_latest_sensor_reading(self):
        """Fetches latest simulated reading correctly."""
        reading = db.get_latest_sensor_reading(1, db_path=self.test_db_path)
        self.assertIsNotNone(reading)
        self.assertEqual(reading["farm_id"], 1)
        self.assertGreaterEqual(reading["soil_moisture_pct"], 0.0)
        self.assertEqual(reading["is_simulated"], 1)

    def test_insert_and_retrieve_sensor_reading(self):
        """Parameterized insert of new telemetry reading."""
        new_reading_id = db.add_sensor_reading(
            farm_id=3,
            soil_moisture_pct=29.5,
            soil_temperature_c=28.0,
            ambient_humidity_pct=65.0,
            rainfall_last_24h_mm=0.0,
            rainfall_forecast_24h_mm=5.0,
            is_simulated=1,
            db_path=self.test_db_path,
        )
        self.assertIsInstance(new_reading_id, int)

        # Check retrieval
        latest = db.get_latest_sensor_reading(3, db_path=self.test_db_path)
        self.assertEqual(latest["soil_moisture_pct"], 29.5)

    def test_record_irrigation_event_and_validation(self):
        """Validates parameterization and constraint enforcement on irrigation log."""
        # Successful insert
        event_id = db.record_irrigation_event(
            farm_id=2,
            water_volume_liters=25000.0,
            irrigation_method="Drip",
            duration_minutes=150,
            recommended_by_system=1,
            notes="Automated test entry",
            db_path=self.test_db_path,
        )
        self.assertIsInstance(event_id, int)

        # Invalid water volume <= 0
        with self.assertRaises(ValueError):
            db.record_irrigation_event(
                farm_id=2,
                water_volume_liters=-500.0,
                irrigation_method="Drip",
                db_path=self.test_db_path,
            )

        # Invalid irrigation method
        with self.assertRaises(ValueError):
            db.record_irrigation_event(
                farm_id=2,
                water_volume_liters=1000.0,
                irrigation_method="FireHose",
                db_path=self.test_db_path,
            )

    def test_foreign_key_constraint(self):
        """Ensure SQLite foreign key prevents inserting logs for non-existent farm."""
        with self.assertRaises(sqlite3.IntegrityError):
            db.record_irrigation_event(
                farm_id=99999,  # Non-existent
                water_volume_liters=5000.0,
                irrigation_method="Drip",
                db_path=self.test_db_path,
            )

    def test_dcdsl_analytical_queries(self):
        """Tests that all 5 advanced DCDSL SQL queries execute cleanly and return non-empty DataFrames."""
        for query_key, meta in db.ANALYTICAL_QUERIES.items():
            df = db.execute_analytical_query(query_key, db_path=self.test_db_path)
            self.assertIsInstance(df, pd.DataFrame)
            self.assertGreater(len(df), 0, f"Query '{query_key}' returned empty dataframe.")

    def test_get_irrigation_history_filtering(self):
        """Verifies filtering irrigation history by specific farm_id vs all farms."""
        all_hist = db.get_irrigation_history(db_path=self.test_db_path)
        self.assertGreaterEqual(len(all_hist), 5)
        self.assertIn("water_volume_liters", all_hist.columns)
        self.assertIn("farm_name", all_hist.columns)

        farm_2_hist = db.get_irrigation_history(farm_id=2, db_path=self.test_db_path)
        self.assertGreaterEqual(len(farm_2_hist), 1)
        self.assertTrue((farm_2_hist["farm_id"] == 2).all())

    def test_get_sensor_readings_history_filtering(self):
        """Verifies telemetry history retrieval and simulation labeling."""
        all_readings = db.get_sensor_readings_history(db_path=self.test_db_path)
        self.assertGreaterEqual(len(all_readings), 5)
        self.assertIn("is_simulated", all_readings.columns)
        self.assertTrue((all_readings["is_simulated"] == 1).all())

        farm_1_readings = db.get_sensor_readings_history(farm_id=1, db_path=self.test_db_path)
        self.assertGreaterEqual(len(farm_1_readings), 1)
        self.assertTrue((farm_1_readings["farm_id"] == 1).all())

    def test_safe_readonly_sql_success(self):
        """Verifies safe SELECT execution via execute_safe_readonly_sql."""
        df = db.execute_safe_readonly_sql("SELECT name, crop_type FROM farms WHERE farm_id = 1;", db_path=self.test_db_path)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertIn("crop_type", df.columns)

    def test_safe_readonly_sql_blocks_destructive_commands(self):
        """Security Guard: DROP, DELETE, UPDATE, INSERT, ALTER must raise PermissionError."""
        destructive_queries = [
            "DROP TABLE farms;",
            "DELETE FROM sensor_readings WHERE farm_id = 1;",
            "UPDATE farms SET area_acres = 999 WHERE farm_id = 1;",
            "INSERT INTO farms (name, owner_name, location, crop_type, area_acres, soil_type) VALUES ('X', 'Y', 'Z', 'Tomato', 1.0, 'Clay');",
            "ALTER TABLE farms ADD COLUMN hacked INTEGER;",
            "TRUNCATE TABLE sensor_readings;",
            "REPLACE INTO farms (farm_id, name) VALUES (1, 'Hacked');",
        ]
        for query in destructive_queries:
            with self.subTest(query=query):
                with self.assertRaises(PermissionError):
                    db.execute_safe_readonly_sql(query, db_path=self.test_db_path)

    def test_dcdsl_join_query_demo(self):
        """Tests parameter-driven JOIN query demo with INNER and LEFT joins."""
        df_inner = db.run_join_query_demo(farm_id=1, join_type="INNER", limit=10, db_path=self.test_db_path)
        self.assertIsInstance(df_inner, pd.DataFrame)
        self.assertIn("farm_name", df_inner.columns)

        df_left = db.run_join_query_demo(crop_filter="Tomato", join_type="LEFT", limit=10, db_path=self.test_db_path)
        self.assertIsInstance(df_left, pd.DataFrame)

    def test_dcdsl_groupby_having_demo(self):
        """Tests GROUP BY & HAVING query demo with consumption threshold slider."""
        df = db.run_groupby_having_demo(min_total_liters=0.0, crop_filter=None, db_path=self.test_db_path)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn("total_liters_used", df.columns)
        self.assertIn("crop_type", df.columns)

    def test_dcdsl_subquery_demo(self):
        """Tests subqueries in SELECT, HAVING, and nested derived tables."""
        for style in ["correlated", "having", "derived"]:
            with self.subTest(style=style):
                df = db.run_subquery_demo(style=style, db_path=self.test_db_path)
                self.assertIsInstance(df, pd.DataFrame)
                self.assertGreater(len(df), 0)

    def test_dcdsl_aggregates_demo(self):
        """Tests SQL Aggregate Functions demo (COUNT, SUM, AVG, MIN, MAX)."""
        df = db.run_aggregates_demo(crop_filter=None, db_path=self.test_db_path)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 1)
        self.assertIn("total_records", df.columns)
        self.assertIn("avg_moisture", df.columns)


class TestSidebarNavigationLogic(unittest.TestCase):
    """Unit tests for sidebar navigation routing, active page state, and dispatch integrity."""

    EXPECTED_NAV_ITEMS = [
        "🏠 Dashboard",
        "💧 Irrigation Advisor",
        "📊 Water Analytics",
        "⏱️ Irrigation History",
        "🌱 Farm Management",
        "🗄️ DCDSL SQL Lab",
        "📡 Telemetry Simulator",
    ]

    def test_all_seven_nav_items_defined(self):
        """Verifies that all 7 required pages are present and unique."""
        self.assertEqual(len(self.EXPECTED_NAV_ITEMS), 7)
        self.assertEqual(len(set(self.EXPECTED_NAV_ITEMS)), 7)

    def test_app_source_contains_all_view_branches(self):
        """Ensures app.py contains concrete dispatch blocks for each navigation option."""
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        self.assertTrue(os.path.exists(app_path))
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()

        for item in self.EXPECTED_NAV_ITEMS:
            with self.subTest(item=item):
                self.assertIn(
                    f'nav_item == "{item}"',
                    code,
                    f"Navigation target '{item}' lacks a dedicated page view handler in app.py"
                )

    def test_quick_actions_map_to_valid_nav_items(self):
        """Verifies that all Quick Action buttons point to valid navigation targets."""
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()

        quick_action_targets = [
            "⏱️ Irrigation History",
            "📊 Water Analytics",
            "🌱 Farm Management",
            "🗄️ DCDSL SQL Lab",
            "📡 Telemetry Simulator",
        ]
        for target in quick_action_targets:
            with self.subTest(target=target):
                self.assertIn(target, self.EXPECTED_NAV_ITEMS)
                self.assertIn(f'st.session_state["active_page"] = "{target}"', code)

    def test_no_destructive_nav_override_loop(self):
        """Verifies that nav_override initialization loop has been removed."""
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertNotIn(
            'st.session_state["nav_override"] = "🏠 Dashboard"',
            code,
            "Found stale nav_override reset loop in app.py which forces dashboard on every rerun!"
        )


class TestPerformanceAndSelectors(unittest.TestCase):
    """Tests for database indexing, caching layer, and farm selector synchronization."""

    def test_database_indexes_created_and_idempotent(self):
        """create_database_indexes must safely create required performance indexes idempotently with conn, path, and keyword db_path."""
        conn = db.get_connection()
        try:
            # 1. Test passing Connection object
            db.create_database_indexes(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            index_names = [row[0] for row in cursor.fetchall()]

            expected_indexes = [
                "idx_sensor_readings_farm_ts",
                "idx_sensor_readings_ts",
                "idx_irrigation_history_farm_ts",
                "idx_irrigation_history_ts",
            ]
            for idx in expected_indexes:
                self.assertIn(idx, index_names, f"Expected database index {idx} not found in sqlite_master!")

            # 2. Test passing keyword argument db_path
            db.create_database_indexes(db_path=db.DEFAULT_DB_PATH)

            # 3. Test passing positional string path
            db.create_database_indexes(db.DEFAULT_DB_PATH)

            # 4. Test passing keyword argument conn
            db.create_database_indexes(conn=conn)

            # 5. Test passing both conn and db_path
            db.create_database_indexes(conn=conn, db_path=db.DEFAULT_DB_PATH)

            # 6. Test default invocation without arguments
            db.create_database_indexes()
        finally:
            conn.close()

    def test_index_creation_preserves_records(self):
        """Index creation must never delete, alter, or drop existing records."""
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM farms;")
            farms_before = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sensor_readings;")
            readings_before = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM irrigation_history;")
            history_before = cursor.fetchone()[0]

            db.create_database_indexes(conn)

            cursor.execute("SELECT COUNT(*) FROM farms;")
            self.assertEqual(cursor.fetchone()[0], farms_before)
            cursor.execute("SELECT COUNT(*) FROM sensor_readings;")
            self.assertEqual(cursor.fetchone()[0], readings_before)
            cursor.execute("SELECT COUNT(*) FROM irrigation_history;")
            self.assertEqual(cursor.fetchone()[0], history_before)
        finally:
            conn.close()

    def test_app_source_selector_synchronization(self):
        """Verifies app.py synchronizes sidebar and main plot selectors with shared callbacks."""
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Callbacks must be defined
        self.assertIn("def on_sidebar_farm_change():", code)
        self.assertIn("def on_main_farm_change():", code)

        # Both selectboxes must bind their callbacks
        self.assertIn('key="sb_farm_select"', code)
        self.assertIn("on_change=on_sidebar_farm_change", code)
        self.assertIn('key="main_farm_select"', code)
        self.assertIn("on_change=on_main_farm_change", code)

        # Selected farm must be fetched from DB record
        self.assertIn('selected_farm = next(f for f in farms if f["farm_id"] == st.session_state["selected_farm_id"])', code)

    def test_app_source_contains_caching_primitives(self):
        """Verifies app.py integrates st.cache_data and st.cache_resource with appropriate TTLs."""
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("@st.cache_resource", code)
        self.assertIn("@st.cache_data", code)
        self.assertIn("get_cached_farms", code)
        self.assertIn("get_cached_latest_sensor_reading", code)
        self.assertIn("get_cached_irrigation_history", code)
        self.assertIn("get_cached_mongo_status", code)


if __name__ == "__main__":
    unittest.main()



