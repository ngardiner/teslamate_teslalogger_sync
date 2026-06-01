import logging
from collections import deque
from datetime import timedelta
from sqlalchemy import text


class ChargingSync:
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
        """Sorted merge-join over two charging streams."""
        tm_window = deque()
        tm_exhausted = False
        tm_iter = iter(tm_stream)
        matches = []
        tl_count = 0

        for tl in tl_stream:
            tl_count += 1
            tl_ts = tl['Datum']

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
                        abs(tl_ts - tm['start_date']) <= self.WINDOW):
                    matches.append(self._merge(tl, tm))
                    tm_window.remove(tm)
                    self.stats['processed'] += 1
                    matched = True
                    break

            if not matched:
                self.stats['skipped'] += 1

        self.logger.info(f"Charging: {tl_count} TeslaLogger, {len(matches)} matched")
        return matches

    def _merge(self, tl, tm):
        return {
            'start_date': min(tl['Datum'], tm['start_date']),
            'end_date': tm['end_date'],
            'car_id': tl['CarID'],
            'charge_energy_added': max(tl.get('charge_energy_added') or 0, tm.get('charge_energy_added') or 0),
            'battery_level_start': tm.get('battery_level_start'),
            'battery_level_end': tm.get('battery_level_end'),
            'battery_level_snapshot': tl.get('battery_level'),
            'charger_power': tl.get('charger_power'),
            'cost': tm.get('cost'),
        }

    def _stream_teslalogger(self):
        query = text("""
            SELECT Datum, CarID, charge_energy_added, battery_level,
                   charger_power, ideal_battery_range_km
            FROM charging ORDER BY Datum
        """)
        with self.tl_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query):
                yield {
                    'Datum': row.Datum,
                    'CarID': row.CarID,
                    'charge_energy_added': row.charge_energy_added,
                    'battery_level': row.battery_level,
                    'charger_power': row.charger_power,
                    'ideal_battery_range_km': row.ideal_battery_range_km,
                }

    def _stream_teslamate(self):
        query = text("""
            SELECT start_date, end_date, car_id, charge_energy_added,
                   start_battery_level, end_battery_level, cost
            FROM charging_processes ORDER BY start_date
        """)
        with self.tm_engine.connect().execution_options(stream_results=True) as conn:
            for row in conn.execute(query):
                yield {
                    'start_date': row.start_date,
                    'end_date': row.end_date,
                    'car_id': row.car_id,
                    'charge_energy_added': row.charge_energy_added,
                    'battery_level_start': row.start_battery_level,
                    'battery_level_end': row.end_battery_level,
                    'cost': row.cost,
                }

    def _get_charging_points(self, car_id, start, end):
        if not self.tl_engine:
            return []
        query = text("""
            SELECT Datum, battery_level, charge_energy_added, charger_power,
                   charger_voltage, charger_phases, charger_actual_current,
                   charger_pilot_current, outside_temp, ideal_battery_range_km, battery_heater
            FROM charging
            WHERE CarID = :car_id AND Datum >= :start AND Datum <= :end
            ORDER BY Datum
        """)
        try:
            with self.tl_engine.connect() as conn:
                result = conn.execute(query, {'car_id': car_id, 'start': start, 'end': end})
                return [dict(row._mapping) for row in result]
        except Exception as e:
            self.logger.warning(f"Failed to fetch charging points: {e}")
            return []

    def log_potential_merges(self, potential_merges):
        self.logger.info(f"Dry run: {len(potential_merges)} charging sessions would be written")
        for i, session in enumerate(potential_merges, 1):
            car_id = session['car_id']
            start = session['start_date']
            end = session['end_date']
            energy = session['charge_energy_added']
            
            # Fetch the telemetry points from TeslaLogger
            points = self._get_charging_points(car_id, start, end)
            
            # Simulate a charging process ID
            simulated_process_id = 3000 + i
            
            self.logger.info(
                f"[Dry Run] Charge Session #{i}: Would insert charging session for CarID={car_id} "
                f"({start} to {end}, energy_added={energy:.1f} kWh, process_id={simulated_process_id})"
            )
            self.logger.info(
                f"  - Inner Telemetry: Would insert {len(points)} high-resolution telemetry points into 'charges' table. Proposed inserts:"
            )
            # Log up to 3 points in detail
            for j, p in enumerate(points[:3], 1):
                self.logger.info(
                    f"    * Point {j}: date={p['Datum']} UTC, battery_level={p['battery_level']}%, "
                    f"power={p['charger_power']}kW, voltage={p['charger_voltage']}V, "
                    f"current={p['charger_actual_current']}A (phases={p['charger_phases']})"
                )
            if len(points) > 3:
                self.logger.info(f"    * ... and {len(points) - 3} more telemetry points.")
