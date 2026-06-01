import logging
import pytest
from datetime import datetime, timedelta
from sync.drives import DriveSync


def make_sync():
    s = DriveSync.__new__(DriveSync)
    s.tl_engine = None
    s.tm_engine = None
    s.dry_run = True
    s.stats = {'added': 0, 'skipped': 0}
    s.logger = logging.getLogger('test')
    return s


T0 = datetime(2024, 1, 1, 10, 0, 0)


def tl(ts, car=1, distance=10.0, speed_max=100):
    return {'StartDate': ts, 'EndDate': ts + timedelta(minutes=30),
            'CarID': car, 'distance': distance, 'speed_max': speed_max}


def tm(ts, car=1, distance=10.0, speed_max=100):
    return {'start_date': ts, 'end_date': ts + timedelta(minutes=30),
            'car_id': car, 'distance': distance, 'speed_max': speed_max}


class TestMatching:
    def test_exact_match(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0)]))
        assert len(matches) == 1
        assert s.stats['added'] == 1

    def test_match_within_five_minutes(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0 + timedelta(minutes=4))]))
        assert len(matches) == 1

    def test_no_match_outside_five_minutes(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0 + timedelta(minutes=6))]))
        assert len(matches) == 0
        assert s.stats['skipped'] == 1

    def test_no_match_different_car(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, car=1)]), iter([tm(T0, car=2)]))
        assert len(matches) == 0

    def test_no_match_distance_too_different(self):
        s = make_sync()
        # 10 km vs 15 km — 5 km difference, over 1 km tolerance
        matches = s._match(iter([tl(T0, distance=10.0)]), iter([tm(T0, distance=15.0)]))
        assert len(matches) == 0

    def test_match_distance_within_tolerance(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, distance=10.0)]), iter([tm(T0, distance=10.5)]))
        assert len(matches) == 1

    def test_merge_takes_max_speed(self):
        s = make_sync()
        matches = s._match(
            iter([tl(T0, speed_max=80)]),
            iter([tm(T0, speed_max=100)])
        )
        assert matches[0]['speed_max'] == 100

    def test_merge_takes_max_distance(self):
        s = make_sync()
        matches = s._match(
            iter([tl(T0, distance=10.5)]),
            iter([tm(T0, distance=10.0)])
        )
        assert matches[0]['distance'] == 10.5


class TestEdgeCases:
    def test_empty_tl(self):
        s = make_sync()
        assert s._match(iter([]), iter([tm(T0)])) == []

    def test_empty_tm(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([]))
        assert matches == []
        assert s.stats['skipped'] == 1

    def test_tm_record_consumed_after_match(self):
        # Two TL records close together — only first should match the TM record
        s = make_sync()
        matches = s._match(
            iter([tl(T0), tl(T0 + timedelta(minutes=1))]),
            iter([tm(T0)])
        )
        assert len(matches) == 1
        assert s.stats['skipped'] == 1


class TestWetRunWelding:
    def test_weld_positions_executed(self, mocker):
        s = make_sync()
        s.dry_run = False
        mock_engine = mocker.MagicMock()
        mock_conn = mocker.MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_result = mocker.MagicMock()
        mock_result.rowcount = 42
        mock_conn.execute.return_value = mock_result
        s.tm_engine = mock_engine

        # Match should execute welding because dry_run = False and id is present
        tm_record = tm(T0)
        tm_record['id'] = 999
        
        matches = s._match(
            iter([tl(T0)]),
            iter([tm_record])
        )
        assert len(matches) == 1
        assert mock_conn.execute.call_count == 1
        
        called_args = mock_conn.execute.call_args[0]
        assert "UPDATE positions" in str(called_args[0])
        assert called_args[1]['drive_id'] == 999
        assert called_args[1]['car_id'] == 1

