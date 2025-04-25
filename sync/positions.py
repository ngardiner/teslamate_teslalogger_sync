import logging
from utils.helpers import haversine_distance
from sqlalchemy import text
from datetime import timedelta

class PositionSync:
    def __init__(self, teslalogger_conn, teslamate_conn, dry_run, test_position, stats, position_limit):
        self.debug_print = 1
        self.teslalogger_conn = teslalogger_conn
        self.teslamate_conn = teslamate_conn
        self.dry_run = dry_run
        self.test_position = test_position
        self.stats = stats  # Reference to the subkey of the stats hash
        self.position_limit = position_limit  # Limit for the number of positions to fetch
        self.logger = logging.getLogger(__name__)

    def sync(self):
        """
        Sync positions between TeslaLogger and TeslaMate databases.
        """
        # Get the list of distinct dates
        distinct_dates = self._get_distinct_dates()
        potential_merges = []

        # Iterate through each date and process positions
        for date in distinct_dates:
            self.logger.info(f"Processing positions for date: {date}")
            
            # Fetch positions for the specific date
            teslalogger_positions = self._fetch_teslalogger_positions(date)
            teslamate_positions = self._fetch_teslamate_positions(date)

            # Validate fetched positions
            if teslalogger_positions is None:
                self.logger.error(f"Failed to fetch TeslaLogger positions for date: {date}")
                return []
            
            if teslamate_positions is None:
                self.logger.error(f"Failed to fetch TeslaMate positions for date: {date}")
                return []

            # Find potential matches
            potential_merges.append(self._find_position_matches(
                teslalogger_positions, 
                teslamate_positions
            ))

        return potential_merges

    def _get_distinct_dates(self):
        """
        Retrieve a list of distinct dates from both databases.
        """
        try:
            query = text("SELECT DISTINCT DATE(Datum) as date FROM pos ORDER BY date")
            result = self.teslalogger_conn.execute(query)
            dates = [row.date for row in result]
            self.logger.info(f"Found {len(dates)} distinct dates in TeslaLogger database")
            return dates
        except Exception as e:
            self.logger.error(f"Error fetching distinct dates: {e}")
            return []

    def _fetch_teslalogger_positions(self, date):
        """
        Fetch positions from TeslaLogger database for a specific date.
        """
        try:
            query = text(f"SELECT * FROM pos WHERE DATE(Datum) = :date")
            result = self.teslalogger_conn.execute(query, {'date': date})
            
            # Convert to list of dictionaries
            positions = []
            for row in result:
                try:
                    position = {
                        'Datum': row.Datum,
                        'CarID': row.CarID,
                        'lat': float(getattr(row, 'lat', None)) if getattr(row, 'lat', None) is not None else None,
                        'lng': float(getattr(row, 'lng', None)) if getattr(row, 'lng', None) is not None else None,
                        'battery_level': getattr(row, 'battery_level', None),
                        'ideal_battery_range_km': getattr(row, 'ideal_battery_range_km', None),
                        'odometer': getattr(row, 'odometer', None),
                        'speed': getattr(row, 'speed', None),
                        'power': getattr(row, 'power', None),
                        'heading': getattr(row, 'heading', None),
                    }
                    positions.append(position)
                except Exception as field_error:
                    self.logger.warning(f"Could not process row: {field_error}")
            
            self.logger.info(f"Fetched {len(positions)} positions from TeslaLogger for date: {date}")
            return positions
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaLogger positions for date {date}: {e}")
            return None

    def _fetch_teslamate_positions(self, date):
        """
        Fetch positions from TeslaMate database for a specific date.
        """
        try:
            query = text(f"SELECT * FROM positions WHERE DATE(date) = :date")
            result = self.teslamate_conn.execute(query, {'date': date})
            
            # Convert to list of dictionaries
            positions = []
            for row in result:
                try:
                    position = {
                        'date': row.date,
                        'car_id': row.car_id,
                        'latitude': float(getattr(row, 'latitude', None)) if getattr(row, 'latitude', None) is not None else None,
                        'longitude': float(getattr(row, 'longitude', None)) if getattr(row, 'longitude', None) is not None else None,
                        'battery_level': getattr(row, 'battery_level', None),
                        'odometer': getattr(row, 'odometer', None),
                        'speed': getattr(row, 'speed', None),
                        'power': getattr(row, 'power', None),
                        'heading': getattr(row, 'heading', None),
                    }
                    positions.append(position)
                except Exception as field_error:
                    self.logger.warning(f"Could not process row: {field_error}")
            
            self.logger.info(f"Fetched {len(positions)} positions from TeslaMate for date: {date}")
            return positions
        
        except Exception as e:
            self.logger.error(f"Error fetching TeslaMate positions for date {date}: {e}")
            return None

    def _find_position_matches(self, teslalogger_pos, teslamate_pos):
        """
        Find matches between TeslaLogger and TeslaMate positions.
        """
        matches = []

        for tl_pos in teslalogger_pos:
            match_found = False

            for tm_pos in teslamate_pos:

                # When debug is enabled, show what the comparative position values are
                if self.debug_print:
                    print(tm_pos)
                    print(tl_pos)
                    self.debug_print = 0

                # Check if positions are identical
                if (tl_pos['Datum'] == tm_pos['date'] and
                    tl_pos['CarID'] == tm_pos['car_id'] and
                    tl_pos['lat'] == tm_pos['latitude'] and
                    tl_pos['lng'] == tm_pos['longitude']):
                    self.stats['identical'] += 1
                    match_found = True
                    break

                # Compare timestamps with a 30-second tolerance
                time_diff = abs(tl_pos['Datum'] - tm_pos['date'])
                if time_diff <= timedelta(seconds=30):
                    car_match = (tl_pos.get('CarID') == tm_pos.get('car_id'))

                    # Calculate distance between positions
                    if (tl_pos['lat'] and tl_pos['lng'] and 
                        tm_pos['latitude'] and tm_pos['longitude']):
                        distance = haversine_distance(
                            tl_pos['lat'], tl_pos['lng'],
                            tm_pos['latitude'], tm_pos['longitude']
                        )
                    else:
                        distance = float('inf')

                    # Validate based on distance threshold
                    if car_match and distance <= 10:  # 10 meters proximity
                        merged_pos = self._merge_position_record(tl_pos, tm_pos)
                        matches.append(merged_pos)
                        self.stats['validated'] += 1
                        match_found = True
                        break

            # If no match was found within 30 seconds, add the position
            if not match_found:
                self.stats['added'] += 1
                matches.append(tl_pos)

        return matches

    def _merge_position_record(self, teslalogger_pos, teslamate_pos):
        # Merge logic for position records
        merged_pos = {
            'timestamp': min(teslalogger_pos['Datum'], teslamate_pos['date']),
            'car_id': teslalogger_pos.get('CarID') or teslamate_pos.get('car_id'),
            'latitude': teslalogger_pos.get('lat') or teslamate_pos.get('latitude'),
            'longitude': teslalogger_pos.get('lng') or teslamate_pos.get('longitude'),
            'battery_level': max(
                teslalogger_pos.get('battery_level', 0) or 0,
                teslamate_pos.get('battery_level', 0) or 0
            ),
            'odometer': max(
                teslalogger_pos.get('odometer', 0) or 0,
                teslamate_pos.get('odometer', 0) or 0
            ),
            'speed': max(
                teslalogger_pos.get('speed', 0) or 0,
                teslamate_pos.get('speed', 0) or 0
            ),
            'power': max(
                teslalogger_pos.get('power', 0) or 0,
                teslamate_pos.get('power', 0) or 0
            ),
            'heading': teslalogger_pos.get('heading') or teslamate_pos.get('heading'),
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
