import logging
from config.config import Config
from database.teslalogger_connection import establish_teslalogger_connection
from database.teslamate_connection import establish_teslamate_connection
from sync.positions import PositionSync
from sync.drives import DriveSync
from sync.charging import ChargingSync
from sync.states import StateSync
import os

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    try:
        # Create configuration instance
        config = Config()

        # Establish database connections
        teslalogger_conn = establish_teslalogger_connection(config)
        teslamate_conn = establish_teslamate_connection(config)

        # Sync configuration from config
        sync_positions = config.SYNC_POSITIONS
        sync_drives = config.SYNC_DRIVES
        sync_charging = config.SYNC_CHARGING
        sync_states = config.SYNC_STATES
        dry_run = config.DRYRUN
        test_position = config.TEST_POSITION

        # Debug logging
        logger.info(f"Sync Configuration:")
        logger.info(f"Positions: {sync_positions}")
        logger.info(f"Drives: {sync_drives}")
        logger.info(f"Charging: {sync_charging}")
        logger.info(f"States: {sync_states}")
        logger.info(f"Dry Run: {dry_run}")

        # Sync engines
        engines = []
        if sync_positions:
            engines.append(PositionSync(teslalogger_conn, teslamate_conn, dry_run, test_position))
        if sync_drives:
            engines.append(DriveSync(teslalogger_conn, teslamate_conn, dry_run))
        if sync_charging:
            engines.append(ChargingSync(teslalogger_conn, teslamate_conn, dry_run))
        if sync_states:
            engines.append(StateSync(teslalogger_conn, teslamate_conn, dry_run))

        # Perform syncs
        for engine in engines:
            logger.info(f"Running sync for {engine.__class__.__name__}")
            potential_merges = engine.sync()
            
            # Log merge details
            if potential_merges:
                engine.log_potential_merges(potential_merges)
            else:
                logger.warning(f"No potential merges found for {engine.__class__.__name__}")

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
