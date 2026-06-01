import pytest
from utils.helpers import haversine_distance


def test_same_point_is_zero():
    assert haversine_distance(-37.8136, 144.9631, -37.8136, 144.9631) == 0.0


def test_known_distance():
    # Melbourne CBD to Melbourne Airport — roughly 19.3 km straight-line
    dist = haversine_distance(-37.8136, 144.9631, -37.6690, 144.8410)
    assert 19_000 < dist < 20_000


def test_small_offset_under_ten_metres():
    # ~0.00001 degree latitude ≈ 1.1 metres
    dist = haversine_distance(-37.0, 145.0, -37.00001, 145.0)
    assert dist < 10


def test_symmetry():
    a = haversine_distance(-37.0, 145.0, -38.0, 146.0)
    b = haversine_distance(-38.0, 146.0, -37.0, 145.0)
    assert abs(a - b) < 0.001
