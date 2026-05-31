import logging
from collections import deque
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
        self.stats = stats
        self.position_limit = position_limit
        self.logger = logging.getLogger(__name__)

    def sync(self):
        """
        Two streaming cursors, one pass each, merge join on timestamp.
        O(n) time, O(window) memory.
        """
        car_ids = self._get_car_ids()
        total_added = 0
        for car_id in car_ids:
            self.logger.info(f"Syncing positions for CarID={car_id}")
            total_added += self._sync_car(car_id)
        return [None] * total_added  # preserve len() contract with main.py

    def _get_car_ids(self):
        try:
            result = self.teslalogger_conn.execute(text("SELECT DISTINCT CarID FROM pos ORDER BY CarID"))
            car_ids = [row.CarID for row in result]
            self.logger.info(f"Found {len(car_ids)} car(s) to process")
            return car_ids
        except Exception as e:
            self.logger.error(f"Error fetching car IDs: {e}")
            return []

    def _sync_car(self, car_id):
        """
        Merge join two sorted streams for a single car.
        Maintains a 30-second sliding window of TeslaMate rows.
        """
        WINDOW = timedelta(seconds=30)
        DISTANCE_THRESHOLD = 10  # metres

        tl_stream = self._stream_teslalogger(car_id)
        tm_stream = self._stream_teslamate(car_id)

        tm_window = deque()   # TeslaMate rows within 30s ahead of current TL row
        tm_exhausted = False
        tm_iter = iter(tm_stream)

        added = 0

        for tl in tl_stream:

            if self.debug_print:
                self.logger.info(f"Sample TL: {tl}")
                self.debug_print = 0

            tl_ts = tl['Datum']

            # Drop TeslaMate rows that are more than 30s behind current TL row
            while tm_window and tm_window[0]['date'] < tl_ts - WINDOW:
                tm_window.popleft()

            # Advance TeslaMate stream to fill window up to 30s ahead of TL row
            if not tm_exhausted:
                while True:
                    try:
                        tm = next(tm_iter)
                        tm_window.append(tm)
                        if tm['date'] > tl_ts + WINDOW:
                            break
                    except StopIteration:
                        tm_exhausted = True
                        break

            # Search window for a match
            match_found = False
            close_time_no_match = False

            for tm in list(tm_window):
                time_diff = abs(tl_ts - tm['date'])

                # Identical record
                if (tl_ts == tm['date'] and
                        tl['CarID'] == tm['car_id'] and
                        tl['lat'] == tm['latitude'] and
                        tl['lng'] == tm['longitude']):
                    self.stats['identical'] += 1
                    tm_window.remove(tm)
                    match_found = True
                    break

                if time_diff <= WINDOW:
                    if (tl['lat'] and tl['lng'] and tm['latitude'] and tm['longitude']):
                        distance = haversine_distance(tl['lat'], tl['lng'], tm['latitude'], tm['longitude'])
                    else:
                        distance = float('inf')

                    if tl['CarID'] == tm['car_id'] and distance <= DISTANCE_THRESHOLD:
                        self.stats['added'] += 1
                        added += 1
                        tm_window.remove(tm)
                        match_found = True
                        break
                    else:
                        close_time_no_match = True

            if not match_found:
                if close_time_no_match:
                    self.stats['invalid'] += 1
                self.stats['added'] += 1
                added += 1

        return added

    def _stream_teslalogger(self, car_id):
        limit = f"LIMIT {self.position_limit}" if self.position_limit else ""
        query = text(f"""
            SELECT * FROM pos
            WHERE CarID = :car_id
            ORDER BY Datum
            {limit}
        """)
        try:
            engine = self.teslalogger_conn.get_bind()
            with engine.connect().execution_options(stream_results=True) as conn:
                for row in conn.execute(query, {'car_id': car_id}):
                    try:
                        yield {
                            'Datum': row.Datum,
                            'CarID': row.CarID,
                            'lat': float(row.lat) if row.lat is not None else None,
                            'lng': float(row.lng) if row.lng is not None else None,
                            'battery_level': getattr(row, 'battery_level', None),
                            'ideal_battery_range_km': getattr(row, 'ideal_battery_range_km', None),
                            'odometer': getattr(row, 'odometer', None),
                            'speed': getattr(row, 'speed', None),
                            'power': getattr(row, 'power', None),
                            'heading': getattr(row, 'heading', None),
                        }
                    except Exception as e:
                        self.logger.warning(f"Skipping TeslaLogger row: {e}")
        except Exception as e:
            self.logger.error(f"Error streaming TeslaLogger: {e}")

    def _stream_teslamate(self, car_id):
        limit = f"LIMIT {self.position_limit}" if self.position_limit else ""
        query = text(f"""
            SELECT * FROM positions
            WHERE car_id = :car_id
            ORDER BY date
            {limit}
        """)
        try:
            engine = self.teslamate_conn.get_bind()
            with engine.connect().execution_options(stream_results=True) as conn:
                for row in conn.execute(query, {'car_id': car_id}):
                    try:
                        yield {
                            'date': row.date,
                            'car_id': row.car_id,
                            'latitude': float(row.latitude) if row.latitude is not None else None,
                            'longitude': float(row.longitude) if row.longitude is not None else None,
                            'battery_level': getattr(row, 'battery_level', None),
                            'odometer': getattr(row, 'odometer', None),
                            'speed': getattr(row, 'speed', None),
                            'power': getattr(row, 'power', None),
                            'heading': getattr(row, 'heading', None),
                        }
                    except Exception as e:
                        self.logger.warning(f"Skipping TeslaMate row: {e}")
        except Exception as e:
            self.logger.error(f"Error streaming TeslaMate: {e}")

    def _merge_position_record(self, teslalogger_pos, teslamate_pos):
        return {
            'timestamp': min(teslalogger_pos['Datum'], teslamate_pos['date']),
            'car_id': teslalogger_pos.get('CarID') or teslamate_pos.get('car_id'),
            'latitude': teslalogger_pos.get('lat') or teslamate_pos.get('latitude'),
            'longitude': teslalogger_pos.get('lng') or teslamate_pos.get('longitude'),
            'battery_level': max(teslalogger_pos.get('battery_level', 0) or 0, teslamate_pos.get('battery_level', 0) or 0),
            'odometer': max(teslalogger_pos.get('odometer', 0) or 0, teslamate_pos.get('odometer', 0) or 0),
            'speed': max(teslalogger_pos.get('speed', 0) or 0, teslamate_pos.get('speed', 0) or 0),
            'power': max(teslalogger_pos.get('power', 0) or 0, teslamate_pos.get('power', 0) or 0),
            'heading': teslalogger_pos.get('heading') or teslamate_pos.get('heading'),
        }

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry Run - Potential Position Merges: {len(potential_merges)}")
        if potential_merges:
            self.logger.warning("DRY RUN MODE ACTIVE — set DRYRUN=0 to apply changes")
