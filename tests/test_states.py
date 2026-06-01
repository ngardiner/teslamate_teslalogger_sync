import logging
import pytest
from datetime import datetime, timedelta
from sync.states import StateSync


def make_sync():
    s = StateSync.__new__(StateSync)
    s.tl_engine = None
    s.tm_engine = None
    s.dry_run = True
    s.stats = {'added': 0, 'skipped': 0}
    s.logger = logging.getLogger('test')
    return s


T0 = datetime(2024, 1, 1, 8, 0, 0)


def tl(ts, car=1, state='sleeping'):
    return {'StartDate': ts, 'EndDate': ts + timedelta(hours=8), 'CarID': car, 'state': state}


def tm(ts, car=1, state='sleeping'):
    return {'start_date': ts, 'end_date': ts + timedelta(hours=8), 'car_id': car, 'state': state}


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

    def test_no_match_different_state(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, state='sleeping')]), iter([tm(T0, state='driving')]))
        assert len(matches) == 0
        assert s.stats['skipped'] == 1

    def test_no_match_outside_window(self):
        s = make_sync()
        matches = s._match(iter([tl(T0)]), iter([tm(T0 + timedelta(minutes=6))]))
        assert len(matches) == 0

    def test_no_match_different_car(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, car=1)]), iter([tm(T0, car=2)]))
        assert len(matches) == 0

    def test_no_match_when_tl_state_is_none(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, state=None)]), iter([tm(T0)]))
        assert len(matches) == 0

    def test_merge_result(self):
        s = make_sync()
        matches = s._match(iter([tl(T0, state='charging')]), iter([tm(T0, state='charging')]))
        assert matches[0]['state'] == 'charging'
        assert matches[0]['car_id'] == 1


class TestEdgeCases:
    def test_empty_tl(self):
        s = make_sync()
        assert s._match(iter([]), iter([tm(T0)])) == []

    def test_empty_tm(self):
        s = make_sync()
        assert s._match(iter([tl(T0)]), iter([])) == []
        assert s.stats['skipped'] == 1

    def test_multiple_state_types(self):
        s = make_sync()
        tl_rows = [tl(T0, state='sleeping'), tl(T0 + timedelta(hours=8), state='driving')]
        tm_rows = [tm(T0, state='sleeping'), tm(T0 + timedelta(hours=8), state='driving')]
        matches = s._match(iter(tl_rows), iter(tm_rows))
        assert len(matches) == 2
