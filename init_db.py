"""
init_db.py - Database Initialization and Seeding Script
======================================================
Usage:
    python3 init_db.py

This script executes database.sql to create tables and seed realistic sample
data for the Smart Irrigation Advisor system.
"""

import sys
import os
import argparse

# Ensure the script directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from db import (
    init_database,
    init_database_safe,
    create_database_indexes,
    get_connection,
    DEFAULT_DB_PATH,
    DEFAULT_SQL_PATH,
)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize or safely update the SQLite database for the Smart Irrigation Advisor."
    )
    parser.add_argument(
        "--reset",
        "--force",
        action="store_true",
        help="Force complete reset: drops existing tables and re-seeds sample data from database.sql.",
    )
    parser.add_argument(
        "--safe",
        action="store_true",
        default=True,
        help="Safe mode (default): creates missing tables without dropping existing user records.",
    )
    args = parser.parse_args()

    print(f"[+] Target SQLite database path: {DEFAULT_DB_PATH}")

    try:
        if args.reset:
            print("[!] Reset flag passed: Dropping existing tables and re-seeding from database.sql...")
            init_database(db_path=DEFAULT_DB_PATH, sql_script_path=DEFAULT_SQL_PATH)
            create_database_indexes(db_path=DEFAULT_DB_PATH)
            print("[✓] Database tables recreated and fresh sample data seeded successfully!\n")
        else:
            print("[+] Running safe initialization (preserving any existing records)...")
            seeded = init_database_safe(db_path=DEFAULT_DB_PATH)
            create_database_indexes(db_path=DEFAULT_DB_PATH)
            if seeded:
                print("[✓] Tables created and initial seed records populated.\n")
            else:
                print("[✓] Existing tables and user records found and preserved intact!\n")
                print("    (Note: To wipe and reset to factory demo data, run: python3 init_db.py --reset)\n")

        # Verify tables and counts
        conn = get_connection(DEFAULT_DB_PATH)
        cursor = conn.cursor()

        tables = ["farms", "sensor_readings", "irrigation_history"]
        print("--- Database Table Status ---")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  • Table '{table}': {count} records")
        conn.close()

        print("\n[✓] Database ready. You can start the application with:")
        print("    streamlit run app.py")

    except Exception as e:
        print(f"[!] Error during database initialization: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

