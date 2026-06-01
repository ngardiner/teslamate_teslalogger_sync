import logging
from collections import deque
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import text
from utils.helpers import haversine_distance

_MAX_TM_WINDOW = 50_000


def _next_month_start(dt):
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(month=dt.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


class PositionSync:
    def __init__(self, tl_engine, tm_engine, dry_run, stats,
                 time_window_seconds=30, distance_threshold_meters=10,
                 tl_timezone='Australia/Melbourne'):
        self.tl_engine = tl_engine
        self.tm_engine = tm_engine
        self.dry_run = dry_run
        self.stats = stats
        self.window = timedelta(seconds=time_window_seconds)
        self.distance_threshold = distance_threshold_meters
        self.tl_tz = ZoneInfo(tl_timezone)
        self.logger = logging.getLogger(__name__)

    def _to_utc(self, naive_local):
        """Convert a naive datetime in TL's local timezone to a naive UTC datetime."""
        return naive_local.replace(tzinfo=self.tl_tz).astimezone(timezone.utc).replace(tzinfo=None)

    def sync(self):
        car_ids = self._get_car_ids()
        total = 0
        for car_id in car_ids:
            self.logger.info(f"Syncing positions for CarID={car_id}")
            chunks = self._get_date_chunks(car_id)
            self.logger.info(f"CarID={car_id}: processing {len(chunks)} monthly chunk(s)")
            for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
                self.logger.info(
                    f"CarID={car_id}: chunk {i}/{len(chunks)} "
                    f"[{chunk_start.date()} – {chunk_end.date()})"
                )
                total += self._merge_join(
                    self._stream_teslalogger(car_id, chunk_start, chunk_end),
                    self._stream_teslamate(car_id, chunk_start, chunk_end),
                )
        return [None] * total

    def _get_car_ids(self):
        with self.tl_engine.connect() as conn:
            result = conn.execute(text("SELECT DISTINCT CarID FROM pos ORDER BY CarID"))
            car_ids = [row.CarID for row in result]
        self.logger.info(f"Found {len(car_ids)} car(s) to process")
        return car_ids

    def _get_date_chunks(self, car_id):
        with self.tl_engine.connect() as conn:
            row = conn.execute(
                text("SELECT MIN(Datum) AS min_d, MAX(Datum) AS max_d FROM pos WHERE CarID = :car_id"),
                {'car_id': car_id},
            ).fetchone()
        if not row or not row.min_d:
            return []

        start = row.min_d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = row.max_d

        chunks = []
        while start <= end:
            chunk_end = _next_month_start(start)
            chunks.append((start, chunk_end))
            start = chunk_end
        return chunks

    def _merge_join(self, tl_stream, tm_stream):
        """Sorted merge-join over two position streams. O(n) time, O(window) memory."""
        import time as _time
        tm_window = deque()
        tm_exhausted = False
        tm_iter = iter(tm_stream)
        added = 0
        tl_count = 0
        tm_fetched = 0
        peak_window = 0
        t_start = _time.monotonic()
        logged_deltas_count = 0
        batch = []

        for tl in tl_stream:
            tl_ts = tl['Datum']
            tl_count += 1
            if tl_count % 5000 == 1:
                elapsed = _time.monotonic() - t_start
                self.logger.info(
                    f"  merge-join progress: tl={tl_count} tl_ts={tl_ts} "
                    f"window={len(tm_window)} peak_window={peak_window} "
                    f"tm_fetched={tm_fetched} elapsed={elapsed:.1f}s"
                )

            while tm_window and tm_window[0]['date'] < tl_ts - self.window:
                tm_window.popleft()

            if not tm_exhausted:
                while True:
                    if len(tm_window) >= _MAX_TM_WINDOW:
                        self.logger.warning(
                            f"TM window hit {_MAX_TM_WINDOW} entries at tl_ts={tl_ts}; "
                            "possible timezone or sort mismatch"
                        )
                        tm_exhausted = True
                        break
                    try:
                        tm = next(tm_iter)
                        tm_window.append(tm)
                        tm_fetched += 1
                        if len(tm_window) > peak_window:
                            peak_window = len(tm_window)
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
                if self.dry_run and logged_deltas_count < 3:
                    battery = tl.get('battery_level')
                    battery_str = f"{battery}%" if battery is not None else "N/A"
                    odometer = tl.get('odometer')
                    odometer_str = f"{odometer}km" if odometer is not None else "N/A"
                    self.logger.info(
                        f"[Dry Run] Position: Would insert raw telemetry point at {tl_ts} UTC "
                        f"for CarID={tl['CarID']} (lat={tl['lat']}, lng={tl['lng']}, "
                        f"battery={battery_str}, odometer={odometer_str}, drive_id=NULL)"
                    )
                    logged_deltas_count += 1

                # Active sync INSERT logic
                if not self.dry_run:
                    batch.append({
                        'date': tl_ts,
                        'latitude': tl['lat'],
                        'longitude': tl['lng'],
                        'speed': tl['speed'],
                        'power': tl['power'],
                        'odometer': tl['odometer'],
                        'ideal_battery_range_km': tl['ideal_battery_range_km'],
                        'battery_level': tl['battery_level'],
                        'car_id': tl['CarID'],
                    })
                    if len(batch) >= 5000:
                        self._bulk_insert_positions(batch)

        if not self.dry_run and batch:
            self._bulk_insert_positions(batch)

        elapsed = _time.monotonic() - t_start
        self.logger.info(
            f"  merge-join done: tl={tl_count} tm_fetched={tm_fetched} "
            f"peak_window={peak_window} elapsed={elapsed:.1f}s"
        )
        return added

    def _stream_teslalogger(self, car_id, chunk_start, chunk_end):
        query = text(f"""
            SELECT Datum, CarID, lat, lng, battery_level,
                   ideal_battery_range_km, odometer, speed, power
            FROM pos
            WHERE CarID = :car_id AND Datum >= :start AND Datum < :end
            ORDER BY Datum
        """)
        with self.tl_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query, {'car_id': car_id, 'start': chunk_start, 'end': chunk_end}):
                try:
                    yield {
                        'Datum': self._to_utc(row.Datum),
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

    def _stream_teslamate(self, car_id, chunk_start, chunk_end):
        # TM stores UTC; chunk boundaries are TL-local — convert before querying
        tm_start = self._to_utc(chunk_start) - self.window
        tm_end = self._to_utc(chunk_end) + self.window
        query = text(f"""
            SELECT date, car_id, latitude, longitude, battery_level,
                   ideal_battery_range_km, odometer, speed, power
            FROM positions
            WHERE car_id = :car_id AND date >= :start AND date < :end
            ORDER BY date
        """)
        with self.tm_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query, {'car_id': car_id, 'start': tm_start, 'end': tm_end}):
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

    def _bulk_insert_positions(self, batch):
        query = text("""
            INSERT INTO positions (
                date, latitude, longitude, speed, power, 
                odometer, ideal_battery_range_km, battery_level, car_id, drive_id
            ) VALUES (
                :date, :latitude, :longitude, :speed, :power, 
                :odometer, :ideal_battery_range_km, :battery_level, :car_id, NULL
            )
        """)
        try:
            with self.tm_engine.connect() as conn:
                conn.execute(query, batch)
                conn.commit()
            self.logger.info(f"  Successfully inserted batch of {len(batch)} position records into TeslaMate")
        except Exception as e:
            self.logger.error(f"Failed to bulk insert positions: {e}")
            raise e
        finally:
            # Explicitly clear batch elements and free memory immediately
            batch.clear()
