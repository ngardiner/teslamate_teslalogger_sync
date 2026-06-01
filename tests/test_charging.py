import logging
import pytest
from datetime import datetime, timedelta
from sync.charging import ChargingSync


def make_sync():
    s = ChargingSync.__new__(ChargingSync)
    s.tl_engine = None
    s.tm_engine = None
    s.dry_run = True
    s.stats = {'processed': 0, 'skipped': 0}
    s.logger = logging.getLogger('test')
    return s


T0 = datetime(2024, 1, 1, 20, 0, 0)


def tl(ts, car=1, energy=25.0, power=11.0):
    return {'Datum': ts, 'CarID': car, 'charge_energy_added': energy,
            'battery_level': 60, 'charger_power': power, 'ideal_battery_range_km': 400.0}


def tm(ts, car=1, energy=25.5):
    return {'start_date': ts, 'end_date': ts + timedelta(hours=2),
            'car_id': car, 'charge_energy_added': energy,
            'battery_level_start': 40, 'battery_level_end': 80, 'cost': 5.50}


class TestMatching:
    def test_exact_match(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0)]))
        assert len(matches) == 1
        assert s.stats['processed'] == 1

    def test_match_within_five_minutes(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0 + timedelta(minutes=4))]))
        assert len(matches) == 1

    def test_no_match_outside_window(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0 + timedelta(minutes=6))]))
        assert len(matches) == 0
        assert s.stats['skipped'] == 1

    def test_no_match_different_car(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, car=1)]), iter([tm(T0, car=2)]))
        assert len(matches) == 0

    def test_merge_takes_max_energy(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, energy=24.0)]), iter([tm(T0, energy=25.5)]))
        assert matches[0]['charge_energy_added'] == 25.5

    def test_merge_preserves_tm_battery_levels(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0)]))
        assert matches[0]['battery_level_start'] == 40
        assert matches[0]['battery_level_end'] == 80

    def test_merge_preserves_cost(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0)]))
        assert matches[0]['cost'] == 5.50


class TestEdgeCases:
    def test_empty_tl(self):
        s = make_sync()
        assert s._match(iter([]), iter([tm(T0)])) == []

    def test_empty_tm(self):
        s = make_sync()
        assert s._match(iter([tl(T0)]), iter([])) == []
        assert s.stats['skipped'] == 1


class TestWetRunTelemetry:
    def test_bulk_insert_charges_executed(self, mocker):
        s = make_sync()
        s.dry_run = False
        mock_engine = mocker.MagicMock()
        mock_conn = mocker.MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        # Capture the batch in-flight before finally: batch.clear() empties it
        captured_batch = []
        def mock_execute(query, batch):
            captured_batch.extend(list(batch))
            return mocker.MagicMock()
        mock_conn.execute.side_effect = mock_execute
        
        s.tm_engine = mock_engine

        # Mock tm record with id to open telemetry collection
        tm_record = tm(T0)
        tm_record['id'] = 777
        
        matches = s._match(
            iter([tl(T0)]),
            iter([tm_record])
        )
        assert len(matches) == 1
        assert mock_conn.execute.call_count == 1
        
        called_args = mock_conn.execute.call_args[0]
        assert "INSERT INTO charges" in str(called_args[0])
        assert captured_batch[0]['charging_process_id'] == 777
        assert captured_batch[0]['battery_level'] == 60


