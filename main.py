import os
import logging
from config.config import load_config
from database.teslalogger_connection import establish_teslalogger_connection
from database.teslamate_connection import establish_teslamate_connection
from sync.positions import PositionSync
from sync.drives import DriveSync
from sync.charging import ChargingSync
from sync.states import StateSync
from utils.logger import setup_logging

def main():
    # Setup logging
    logger = setup_logging()

    try:
        # Load configuration
        config = load_config()

        # Establish database connections
        teslalogger_conn = establish_teslalogger_connection(config)
        teslamate_conn = establish_teslamate_connection(config)

        # Determine sync mode
        dry_run = os.getenv('DRYRUN', '1') == '1'
        test_position = os.getenv('TEST_POSITION', '0') == '1'

        # Initialize sync engines
        sync_engines = [
            PositionSync(teslalogger_conn, teslamate_conn, dry_run, test_position),
            DriveSync(teslalogger_conn, teslamate_conn, dry_run),
            ChargingSync(teslalogger_conn, teslamate_conn, dry_run),
            StateSync(teslalogger_conn, teslamate_conn, dry_run)
        ]

        # Perform sync for each engine
        for engine in sync_engines:
            potential_merges = engine.sync()
            
            if dry_run:
                engine.log_potential_merges(potential_merges)

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise

if __name__ == "__main__":
    main()
