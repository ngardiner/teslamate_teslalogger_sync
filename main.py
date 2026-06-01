import logging
from config.config import Config
from database.teslalogger_connection import establish_teslalogger_connection
from database.teslamate_connection import establish_teslamate_connection
from sync.positions import PositionSync
from sync.drives import DriveSync
from sync.charging import ChargingSync
from sync.states import StateSync


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    config = Config()
    sc = config.sync_config

    logger.info(
        f"Starting sync — positions={sc['sync_positions']} drives={sc['sync_drives']} "
        f"charging={sc['sync_charging']} states={sc['sync_states']} "
        f"dry_run={sc['dry_run']}"
    )

    tl_engine = establish_teslalogger_connection(config)
    tm_engine = establish_teslamate_connection(config)

    try:
        stats = {
            'positions': {'identical': 0, 'invalid': 0, 'added': 0},
            'drives':    {'added': 0, 'skipped': 0},
            'charging':  {'processed': 0, 'skipped': 0},
            'states':    {'added': 0, 'skipped': 0},
        }

        engines = []
        if sc['sync_positions']:
            engines.append(PositionSync(
                tl_engine, tm_engine, sc['dry_run'], stats['positions'],
                time_window_seconds=sc['position_time_window'],
                distance_threshold_meters=sc['position_distance_threshold'],
                tl_timezone=sc['tl_timezone'],
            ))
        if sc['sync_drives']:
            engines.append(DriveSync(tl_engine, tm_engine, sc['dry_run'], stats['drives']))
        if sc['sync_charging']:
            engines.append(ChargingSync(tl_engine, tm_engine, sc['dry_run'], stats['charging']))
        if sc['sync_states']:
            engines.append(StateSync(tl_engine, tm_engine, sc['dry_run'], stats['states']))

        for engine in engines:
            name = engine.__class__.__name__
            logger.info(f"Running {name}")
            merges = engine.sync()
            if sc['dry_run']:
                engine.log_potential_merges(merges)
            else:
                logger.info(f"{name}: {len(merges)} records processed")

        logger.info(f"Sync complete — stats: {stats}")

    finally:
        tl_engine.dispose()
        tm_engine.dispose()


if __name__ == "__main__":
    main()
