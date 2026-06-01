import logging
from collections import deque
from datetime import timedelta
from sqlalchemy import text
from utils.helpers import haversine_distance


class PositionSync:
    def __init__(self, tl_engine, tm_engine, dry_run, stats, position_limit,
                 time_window_seconds=30, distance_threshold_meters=10):
        self.tl_engine = tl_engine
        self.tm_engine = tm_engine
        self.dry_run = dry_run
        self.stats = stats
        self.position_limit = position_limit
        self.window = timedelta(seconds=time_window_seconds)
        self.distance_threshold = distance_threshold_meters
        self.logger = logging.getLogger(__name__)

    def sync(self):
        car_ids = self._get_car_ids()
        total = 0
        for car_id in car_ids:
            self.logger.info(f"Syncing positions for CarID={car_id}")
            total += self._merge_join(
                self._stream_teslalogger(car_id),
                self._stream_teslamate(car_id),
            )
        return [None] * total

    def _get_car_ids(self):
        with self.tl_engine.connect() as conn:
            result = conn.execute(text("SELECT DISTINCT CarID FROM pos ORDER BY CarID"))
            car_ids = [row.CarID for row in result]
        self.logger.info(f"Found {len(car_ids)} car(s) to process")
        return car_ids

    def _merge_join(self, tl_stream, tm_stream):
        """
        Sorted merge-join over two position streams.
        O(n) time, O(window) memory.
        """
        tm_window = deque()
        tm_exhausted = False
        tm_iter = iter(tm_stream)
        added = 0

        for tl in tl_stream:
            tl_ts = tl['Datum']

            while tm_window and tm_window[0]['date'] < tl_ts - self.window:
                tm_window.popleft()

            if not tm_exhausted:
                while True:
                    try:
                        tm = next(tm_iter)
                        tm_window.append(tm)
                        if tm['date'] > tl_ts + self.window:
                            break
                    except StopIteration:
                        tm_exhausted = True
                        break

            match_found = False
            close_time_no_match = False

            for tm in list(tm_window):
                time_diff = abs(tl_ts - tm['date'])

                if (tl_ts == tm['date'] and
                        tl['CarID'] == tm['car_id'] and
                        tl['lat'] == tm['latitude'] and
                        tl['lng'] == tm['longitude']):
                    self.stats['identical'] += 1
                    tm_window.remove(tm)
                    match_found = True
                    break

                if time_diff <= self.window:
                    if tl['lat'] and tl['lng'] and tm['latitude'] and tm['longitude']:
                        distance = haversine_distance(tl['lat'], tl['lng'], tm['latitude'], tm['longitude'])
                    else:
                        distance = float('inf')

                    if tl['CarID'] == tm['car_id'] and distance <= self.distance_threshold:
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
            SELECT Datum, CarID, lat, lng, battery_level,
                   ideal_battery_range_km, odometer, speed, power
            FROM pos
            WHERE CarID = :car_id
            ORDER BY Datum
            {limit}
        """)
        with self.tl_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query, {'car_id': car_id}):
                try:
                    yield {
                        'Datum': row.Datum,
                        'CarID': row.CarID,
                        'lat': float(row.lat) if row.lat is not None else None,
                        'lng': float(row.lng) if row.lng is not None else None,
                        'battery_level': row.battery_level,
                        'ideal_battery_range_km': row.ideal_battery_range_km,
                        'odometer': row.odometer,
                        'speed': row.speed,
                        'power': row.power,
                    }
                except Exception as e:
                    self.logger.warning(f"Skipping TeslaLogger row: {e}")

    def _stream_teslamate(self, car_id):
        limit = f"LIMIT {self.position_limit}" if self.position_limit else ""
        query = text(f"""
            SELECT date, car_id, latitude, longitude, battery_level,
                   ideal_battery_range_km, odometer, speed, power
            FROM positions
            WHERE car_id = :car_id
            ORDER BY date
            {limit}
        """)
        with self.tm_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query, {'car_id': car_id}):
                try:
                    yield {
                        'date': row.date,
                        'car_id': row.car_id,
                        'latitude': float(row.latitude) if row.latitude is not None else None,
                        'longitude': float(row.longitude) if row.longitude is not None else None,
                        'battery_level': row.battery_level,
                        'odometer': row.odometer,
                        'ideal_battery_range_km': row.ideal_battery_range_km,
                        'speed': row.speed,
                        'power': row.power,
                    }
                except Exception as e:
                    self.logger.warning(f"Skipping TeslaMate row: {e}")

    def log_potential_merges(self, potential_merges):
        self.logger.info(
            f"Dry run: {len(potential_merges)} position records would be written "
            f"({self.stats['identical']} identical, {self.stats['invalid']} invalid)"
        )
