import logging
from collections import deque
from datetime import timedelta
from sqlalchemy import text


class StateSync:
    WINDOW = timedelta(minutes=5)

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
        """Sorted merge-join over two state streams."""
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
                if (tl['CarID'] == tm['car_id'] and
                        abs(tl_ts - tm['start_date']) <= self.WINDOW and
                        tl.get('state') is not None and
                        tl.get('state') == tm.get('state')):
                    matches.append(self._merge(tl, tm))
                    tm_window.remove(tm)
                    self.stats['added'] += 1
                    matched = True
                    break

            if not matched:
                self.stats['skipped'] += 1

        self.logger.info(f"States: {tl_count} TeslaLogger, {len(matches)} matched")
        return matches

    def _merge(self, tl, tm):
        return {
            'start_date': min(tl['StartDate'], tm['start_date']),
            'end_date': max(tl.get('EndDate') or tm['end_date'], tm['end_date']),
            'car_id': tl['CarID'],
            'state': tl.get('state') or tm.get('state'),
        }

    def _stream_teslalogger(self):
        query = text("""
            SELECT StartDate, EndDate, CarID, state
            FROM state ORDER BY StartDate
        """)
        with self.tl_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query):
                yield {
                    'StartDate': row.StartDate,
                    'EndDate': row.EndDate,
                    'CarID': row.CarID,
                    'state': row.state,
                }

    def _stream_teslamate(self):
        query = text("""
            SELECT start_date, end_date, car_id, state
            FROM states ORDER BY start_date
        """)
        with self.tm_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query):
                yield {
                    'start_date': row.start_date,
                    'end_date': row.end_date,
                    'car_id': row.car_id,
                    'state': str(row.state) if row.state is not None else None,
                }

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry run: {len(potential_merges)} states would be written")
