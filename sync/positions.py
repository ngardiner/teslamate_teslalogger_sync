import logging
from utils.helpers import haversine_distance

class PositionSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run, test_position):
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.test_position = test_position
        self.logger = logging.getLogger(__name__)

    def sync(self):
        # Fetch positions from both databases
        teslalogger_positions = self._fetch_teslalogger_positions()
        teslamate_positions = self._fetch_teslamate_positions()

        # Find potential matches
        potential_merges = self._find_position_matches(
            teslalogger_positions, 
            teslamate_positions
        )

        return potential_merges

    def _find_position_matches(self, teslalogger_pos, teslamate_pos):
        matches = []
        
        for tl_pos in teslalogger_pos:
            for tm_pos in teslamate_pos:
                # Match criteria
                if (abs((tl_pos['Datum'] - tm_pos['date']).total_seconds()) <= 30 and
                    haversine_distance(
                        tl_pos['lat'], tl_pos['lng'],
                        tm_pos['latitude'], tm_pos['longitude']
                    ) <= 10):  # 10 meters
                    
                    merged_pos = self._merge_position_record(tl_pos, tm_pos)
                    matches.append(merged_pos)

        return matches

    def _merge_position_record(self, teslalogger_pos, teslamate_pos):
        # Merge logic from previous implementation
        merged_pos = {
            'timestamp': max(teslalogger_pos['Datum'], teslamate_pos['date']),
            'latitude': teslamate_pos['latitude'],
            'longitude': teslamate_pos['longitude'],
            # ... other merged fields
        }
        return merged_pos

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry Run - Potential Position Merges: {len(potential_merges)}")
        for merge in potential_merges:
            self.logger.info(f"Would merge position: {merge}")

        if potential_merges:
            self.logger.warning("""
            DRY RUN MODE ACTIVE
            Potential position merges detected.
            To apply changes, set DRYRUN=0
            """)

    def _fetch_teslalogger_positions(self):
        # Fetch positions from TeslaLogger database
        # Implement database query
        pass

    def _fetch_teslamate_positions(self):
        # Fetch positions from TeslaMate database
        # Implement database query
        pass
