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


def test_temperature_fallback_stored(manager, good_reading):
    # Current behaviour: a TMP117 failure falls back to the BME280 temperature, which is still stored. See plans/README.md "Open questions".
    assert manager.validate_data_point(good_reading(temp_ok=False, atmospheric_ok=True)) is True
