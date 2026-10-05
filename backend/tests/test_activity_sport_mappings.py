"""Explicit provider sport aliases and unknown-sport behavior."""

from app.connectors.strava.type_map import resolve_discipline as resolve_strava
from app.connectors.whoop.type_map import resolve_discipline as resolve_whoop


def test_strava_distinguishes_mountain_biking_from_motorcycle_enduro():
    index = {
        "mountain_biking": 1,
        "enduro": 2,
        "gravel_cycling": 3,
        "sailing": 4,
        "hiking": 5,
        "walking": 6,
        "swimming": 7,
        "rowing": 8,
        "yoga": 9,
        "pilates": 10,
    }
    assert resolve_strava("MountainBikeRide", index) == (1, "strava:MountainBikeRide->mountain_biking")
    assert resolve_strava("Enduro", index) == (2, None)
    assert resolve_strava("GravelRide", index) == (3, "strava:GravelRide->gravel_cycling")
    assert resolve_strava("Sail", index) == (4, "strava:Sail->sailing")
    assert resolve_strava("CheeseRolling", index) == (None, None)


def test_whoop_common_sports_and_unknown_types():
    index = {
        "mountain_biking": 1,
        "enduro": 2,
        "gravel_cycling": 3,
        "sailing": 4,
        "hiking": 5,
        "walking": 6,
        "swimming": 7,
        "rowing": 8,
        "yoga": 9,
        "pilates": 10,
    }
    assert resolve_whoop("mountain_biking", index) == (1, None)
    assert resolve_whoop("enduro", index) == (2, None)
    assert resolve_whoop("sailing", index) == (4, None)
    assert resolve_whoop("unmapped sport", index) == (None, None)
