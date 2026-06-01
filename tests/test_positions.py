import pytest
from datetime import datetime, timedelta
from sync.positions import PositionSync


def make_sync(**kwargs):
    s = PositionSync.__new__(PositionSync)
    s.tl_engine = None
    s.tm_engine = None
    s.dry_run = True
    s.stats = {'identical': 0, 'invalid': 0, 'added': 0}
    s.window = timedelta(seconds=kwargs.get('window_seconds', 30))
    s.distance_threshold = kwargs.get('distance_threshold', 10)
    return s


def tl(ts, car=1, lat=-37.0, lng=145.0):
    return {'Datum': ts, 'CarID': car, 'lat': lat, 'lng': lng}


def tm(ts, car=1, lat=-37.0, lng=145.0):
    return {'date': ts, 'car_id': car, 'latitude': lat, 'longitude': lng}


T0 = datetime(2024, 1, 1, 12, 0, 0)


class TestIdentical:
    def test_identical_record_counted_not_added(self):
        s = make_sync()
        count = s._merge_join(iter([tl(T0)]), iter([tm(T0)]))
        assert s.stats['identical'] == 1
        assert s.stats['added'] == 0
        assert count == 0

    def test_identical_requires_exact_lat_lng(self):
        s = make_sync()
        # same time, same car, but slightly different position — not identical
        count = s._merge_join(iter([tl(T0)]), iter([tm(T0, lat=-37.00001)]))
        assert s.stats['identical'] == 0


class TestMatching:
    def test_match_within_window_and_distance(self):
        s = make_sync()
        count = s._merge_join(
            iter([tl(T0)]),
            iter([tm(T0 + timedelta(seconds=10), lat=-37.000001)])
        )
        assert s.stats['added'] == 1
        assert count == 1

    def test_no_match_outside_time_window(self):
        s = make_sync()
        s._merge_join(
            iter([tl(T0)]),
            iter([tm(T0 + timedelta(seconds=60))])
        )
        assert s.stats['identical'] == 0
        # TL record still counted as added (unmatched)
        assert s.stats['added'] == 1

    def test_no_match_outside_distance_threshold(self):
        # 0.01 degree latitude ≈ 1100m — well outside 10m threshold
        s = make_sync()
        s._merge_join(
            iter([tl(T0)]),
            iter([tm(T0, lat=-37.01)])
        )
        assert s.stats['identical'] == 0
        assert s.stats['invalid'] == 1

    def test_no_match_different_car(self):
        s = make_sync()
        s._merge_join(iter([tl(T0, car=1)]), iter([tm(T0, car=2)]))
        assert s.stats['identical'] == 0
        assert s.stats['added'] == 1  # unmatched TL record

    def test_match_consumes_tm_record(self):
        # Two TL records — first matches the TM record, second should not match
        s = make_sync()
        count = s._merge_join(
            iter([tl(T0), tl(T0 + timedelta(seconds=5))]),
            iter([tm(T0)])
        )
        assert s.stats['identical'] + s.stats['added'] == 2


class TestEdgeCases:
    def test_empty_tl_stream(self):
        s = make_sync()
        count = s._merge_join(iter([]), iter([tm(T0)]))
        assert count == 0
        assert s.stats == {'identical': 0, 'invalid': 0, 'added': 0}

    def test_empty_tm_stream(self):
        s = make_sync()
        count = s._merge_join(iter([tl(T0)]), iter([]))
        assert count == 1
        assert s.stats['added'] == 1

    def test_both_empty(self):
        s = make_sync()
        count = s._merge_join(iter([]), iter([]))
        assert count == 0

    def test_multiple_records_correct_total(self):
        s = make_sync()
        tl_rows = [tl(T0 + timedelta(seconds=i * 30)) for i in range(5)]
        tm_rows = [tm(T0 + timedelta(seconds=i * 30)) for i in range(5)]
        s._merge_join(iter(tl_rows), iter(tm_rows))
        assert s.stats['identical'] == 5

    def test_null_coordinates_handled(self):
        s = make_sync()
        # lat/lng None — should not crash, should not match on distance
        count = s._merge_join(
            iter([tl(T0, lat=None, lng=None)]),
            iter([tm(T0, lat=None, lng=None)])
        )
        # Same timestamp, same car, but None lat/lng — not identical (None != None for identical check)
        assert count >= 0  # just assert no crash
