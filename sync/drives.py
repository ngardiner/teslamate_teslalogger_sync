import logging
from collections import deque
from datetime import timedelta
from sqlalchemy import text


class DriveSync:
    WINDOW = timedelta(minutes=5)
    DISTANCE_TOLERANCE_KM = 1.0

    def __init__(self, tl_engine, tm_engine, dry_run, stats):
        self.tl_engine = tl_engine
        self.tm_engine = tm_engine
        self.dry_run = dry_run
        self.stats = stats
        self.logger = logging.getLogger(__name__)

    def sync(self):
        return self._match(
            self._stream_teslalogger(),
            self._stream_teslamate(),
        )

    def _match(self, tl_stream, tm_stream):
        """Sorted merge-join over two drive streams."""
        tm_window = deque()
        tm_exhausted = False
        tm_iter = iter(tm_stream)
        matches = []
        tl_count = 0

        for tl in tl_stream:
            tl_count += 1
            tl_ts = tl['StartDate']

            while tm_window and tm_window[0]['start_date'] < tl_ts - self.WINDOW:
                tm_window.popleft()

            if not tm_exhausted:
                while True:
                    try:
                        tm = next(tm_iter)
                        tm_window.append(tm)
                        if tm['start_date'] > tl_ts + self.WINDOW:
                            break
                    except StopIteration:
                        tm_exhausted = True
                        break

            matched = False
            for tm in list(tm_window):
                if tl['CarID'] != tm['car_id']:
                    continue
                if abs(tl_ts - tm['start_date']) > self.WINDOW:
                    continue
                tl_dist = tl.get('distance')
                tm_dist = tm.get('distance')
                if (tl_dist is not None and tm_dist is not None and
                        abs(tl_dist - tm_dist) >= self.DISTANCE_TOLERANCE_KM):
                    continue
                merged = self._merge(tl, tm)
                matches.append(merged)
                tm_window.remove(tm)
                self.stats['added'] += 1
                matched = True
                if not self.dry_run and merged.get('id') is not None:
                    self._weld_positions(merged)
                break

            if not matched:
                self.stats['skipped'] += 1

        self.logger.info(f"Drives: {tl_count} TeslaLogger, {len(matches)} matched")
        return matches

    def _merge(self, tl, tm):
        return {
            'id': tm.get('id'),
            'start_date': min(tl['StartDate'], tm['start_date']),
            'end_date': max(tl.get('EndDate') or tm['end_date'], tm['end_date']),
            'car_id': tl['CarID'],
            'distance': max(tl.get('distance') or 0, tm.get('distance') or 0),
            'speed_max': max(tl.get('speed_max') or 0, tm.get('speed_max') or 0),
        }

    def _stream_teslalogger(self):
        query = text("""
            SELECT StartDate, EndDate, CarID, speed_max,
                   (COALESCE(distance_up_km, 0) + COALESCE(distance_down_km, 0)
                    + COALESCE(distance_flat_km, 0)) AS distance
            FROM drivestate ORDER BY StartDate
        """)
        with self.tl_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query):
                yield {
                    'StartDate': row.StartDate,
                    'EndDate': row.EndDate,
                    'CarID': row.CarID,
                    'distance': row.distance,
                    'speed_max': row.speed_max,
                }

    def _stream_teslamate(self):
        query = text("""
            SELECT id, start_date, end_date, car_id, distance, speed_max
            FROM drives ORDER BY start_date
        """)
        with self.tm_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query):
                yield {
                    'id': row.id,
                    'start_date': row.start_date,
                    'end_date': row.end_date,
                    'car_id': row.car_id,
                    'distance': row.distance,
                    'speed_max': row.speed_max,
                }


    def _count_positions_in_range(self, car_id, start, end):
        if not self.tl_engine:
            return 0
        query = text("""
            SELECT COUNT(*) AS cnt 
            FROM pos 
            WHERE CarID = :car_id AND Datum >= :start AND Datum <= :end
        """)
        try:
            with self.tl_engine.connect() as conn:
                row = conn.execute(query, {'car_id': car_id, 'start': start, 'end': end}).fetchone()
                return row.cnt if row else 0
        except Exception as e:
            self.logger.warning(f"Failed to count positions in range: {e}")
            return 0

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry run: {len(potential_merges)} drives would be written")
        for i, drive in enumerate(potential_merges, 1):
            car_id = drive['car_id']
            start = drive['start_date']
            end = drive['end_date']
            distance = drive['distance']
            speed_max = drive['speed_max']
            
            # Count how many raw positions fall in this timeframe
            pos_count = self._count_positions_in_range(car_id, start, end)
            
            # Simulate a primary key ID for dry run visual plumbing
            simulated_drive_id = 2000 + i
            
            self.logger.info(
                f"[Dry Run] Drive #{i}: Would insert drive session for CarID={car_id} "
                f"({start} to {end}, distance={distance:.1f}km, max_speed={speed_max}km/h)"
            )
            self.logger.info(
                f"  - Relational Weld: Would weld {pos_count} position records to Drive ID {simulated_drive_id} using:\n"
                f"    UPDATE positions SET drive_id = {simulated_drive_id} "
                f"WHERE car_id = {car_id} AND date >= '{start}' AND date <= '{end}' AND drive_id IS NULL;"
            )

    def _weld_positions(self, merged):
        query = text("""
            UPDATE positions 
            SET drive_id = :drive_id 
            WHERE car_id = :car_id 
              AND date >= :start_date 
              AND date <= :end_date 
              AND drive_id IS NULL
        """)
        try:
            with self.tm_engine.connect() as conn:
                result = conn.execute(query, {
                    'drive_id': merged['id'],
                    'car_id': merged['car_id'],
                    'start_date': merged['start_date'],
                    'end_date': merged['end_date']
                })
                conn.commit()
                rows_updated = result.rowcount
            if rows_updated > 0:
                self.logger.info(
                    f"  Successfully welded {rows_updated} positions to Drive ID {merged['id']} "
                    f"({merged['start_date']} – {merged['end_date']})"
                )
        except Exception as e:
            self.logger.error(f"Failed to weld positions to drive {merged.get('id')}: {e}")
            raise e

