import pytest


def test_good_reading(manager, good_reading):
    assert manager.validate_data_point(good_reading()) is True


def test_warmup_rejected(manager, good_reading):
    assert manager.validate_data_point(good_reading(sensor_status="warm-up")) is False


def test_atmospheric_failure_rejected(manager, good_reading):
    assert manager.validate_data_point(good_reading(atmospheric_ok=False)) is False


@pytest.mark.parametrize("field,value", [
    ("tempC", 60), ("humRH", 101), ("pres_hPa", 850),
    ("tvoc", 70000), ("eco2", 399), ("aqi", 0), ("aqi", 6),
])
def test_out_of_range_rejected(manager, good_reading, field, value):
    assert manager.validate_data_point(good_reading(**{field: value})) is False


def test_missing_tvoc_rejected(manager, good_reading):
    reading = good_reading()
    del reading["tvoc"]
    assert manager.validate_data_point(reading) is False


def test_temperature_fallback_not_stored(manager, good_reading):
    # TMP117 fallback values are display-only (plan 011)
    assert manager.validate_data_point(good_reading(temp_ok=False, atmospheric_ok=True)) is False
