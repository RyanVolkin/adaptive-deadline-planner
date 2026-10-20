import pytest

from app.estimation import EstimationEngine


@pytest.fixture
def engine():
    return EstimationEngine()


@pytest.mark.parametrize("actual, original, expected", [
    (150, 100, 1.5),
    (0, 100, None),
])
def test_estimate_ratio(engine, actual, original, expected):
    assert engine.estimate_ratio(actual, original) == expected


@pytest.mark.parametrize("ratios, expected", [
    ([], 1.0),
    ([0.2, 2.4], 1.3),
    ([0.1, 0.2], 0.5),
    ([2.0, 3.0], 2.0),
])
def test_history_factor(engine, ratios, expected):
    assert engine.history_factor(ratios) == pytest.approx(expected)


@pytest.mark.parametrize("original, factor, expected", [
    (100, 1.234, 124),
    (100, 1.1, 110),
])
def test_starting_estimate(engine, original, factor, expected):
    assert engine.starting_estimate(original, factor) == expected


def test_pace_total(engine):
    assert engine.pace_total(50, 25) == 200


@pytest.mark.parametrize("starting, actual, pct, expected", [
    (600, 50, 9, 600),
    (600, 0, 50, 600),
    (600, 50, 30, 384),
    (600, 50, 25, 400),
    (600, 200, 10, 1200),
])
def test_adjusted_estimate(engine, starting, actual, pct, expected):
    adjusted = engine.adjusted_estimate(starting, actual, pct)
    assert adjusted == expected
    assert isinstance(adjusted, int)


@pytest.mark.parametrize("adjusted, pct, expected", [
    (400, 25, 300),
    (1200, 10, 1080),
    (101, 50, 51),
    (400, 100, 0),
])
def test_remaining_work(engine, adjusted, pct, expected):
    assert engine.remaining_work(adjusted, pct) == expected
